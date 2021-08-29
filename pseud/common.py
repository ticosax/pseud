import asyncio
import builtins
from collections import Counter
import contextlib
import datetime as dt
import functools
import inspect
import logging
import pprint
import sys
import textwrap
import traceback
import uuid

import zmq
import zmq.asyncio
import zope.component
import zope.interface

from . import interfaces
from .interfaces import (AUTHENTICATED, EMPTY_DELIMITER, ERROR,  # NOQA
                         HEARTBEAT, HELLO, OK, UNAUTHORIZED, VERSION, WORK,
                         IAuthenticationBackend, IHeartbeatBackend,
                         ServiceNotFoundError)
from .packer import Packer  # NOQA
from .utils import (create_local_registry, get_rpc_callable,  # NOQA
                    register_rpc)

logger = logging.getLogger(__name__)

_marker = object()

MAX_EHOSTUNREACH_RETRY = 3

internal_exceptions = tuple(name for name in dir(interfaces) if
                            inspect.isclass(getattr(interfaces, name)) and
                            issubclass(getattr(interfaces, name), Exception))


class DummyFuture:
    """
    When future is gone replace it with this one to display
    incoming messages associating to ghost future.
    """
    def set_exception(self, exception):
        try:
            raise exception
        except Exception:
            logger.exception('Captured exception from main loop')
            raise


def format_remote_traceback(traceback):
    pivot = '\n{}'.format(3 * 4 * ' ')  # like three tabs
    return textwrap.dedent("""
        -- Beginning of remote traceback --
            {}
        -- End of remote traceback --
        """.format(pivot.join(str(traceback).splitlines())))


UTC = dt.timezone.utc


def handle_result(future):
    try:
        future.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception('Unhandled Exception')
        raise


async def read_forever(socket, callback, copy=False):
    while True:
        result = await socket.recv_multipart(copy=copy)
        await callback(result)


class AttributeWrapper(object):
    def __init__(self, rpc, name=None, user_id=None):
        self.rpc = rpc
        self._part_names = name.split('.') if name is not None else []
        self.user_id = user_id

    def __getattr__(self, name, default=_marker):
        try:
            if default is _marker:
                return super().__getattr__(name)
            return super().__getattr__(name, default=default)
        except AttributeError:
            self.name = name
            return self

    def name_getter(self):
        return '.'.join(self._part_names)

    def name_setter(self, value):
        self._part_names.append(value)

    name = property(name_getter, name_setter)

    def __call__(self, *args, **kw):
        user_id = self.user_id or self.rpc.peer_routing_id
        return self.rpc.send_work(user_id, self.name, *args, **kw)


class BaseRPC(object):
    def __init__(self, user_id=None, routing_id=None, peer_routing_id=None,
                 context=None, loop=None,
                 security_plugin='noop_auth_backend',
                 public_key=None, secret_key=None,
                 peer_public_key=None, timeout=5,
                 password=None, heartbeat_plugin='noop_heartbeat_backend',
                 proxy_to=None, registry=None, translation_table=None):
        self.user_id = user_id
        self.routing_id = routing_id
        self.context = context or self._make_context()
        self.peer_routing_id = peer_routing_id
        self.security_plugin = security_plugin
        self.future_pool = {}
        self.initialized = False
        self.auth_backend = zope.component.getAdapter(
            self,
            IAuthenticationBackend,
            name=self.security_plugin
        )
        self.public_key = public_key
        self.secret_key = secret_key
        self.peer_public_key = peer_public_key
        self.password = password
        self.timeout = timeout
        self.heartbeat_backend = zope.component.getAdapter(
            self,
            IHeartbeatBackend,
            name=heartbeat_plugin)
        self.proxy_to = proxy_to
        self.reader = None
        self.loop = loop or asyncio.get_event_loop()
        self.reader = None
        self.registry = (registry if registry is not None
                         else create_local_registry(user_id or ''))
        self.socket = None
        self.packer = Packer(translation_table)

    def __getattr__(self, name, default=_marker):
        try:
            if default is _marker:
                return super().__getattr__(name)
            return super().__getattr__(name, default=default)
        except AttributeError:
            if not self.initialized:
                raise RuntimeError('You must connect or bind first'
                                   ' in order to call {!r}'.format(name))
            return AttributeWrapper(self, name=name)

    def send_to(self, user_id):
        return AttributeWrapper(self, user_id=user_id)

    def _setup_socket(self, probing=False):
        if self.socket is None:
            self.socket = self.context.socket(self.socket_type)
        if self.routing_id:
            self.socket.setsockopt(zmq.IDENTITY, self.routing_id)
        if self.socket_type == zmq.ROUTER:
            self.socket.setsockopt(zmq.ROUTER_MANDATORY, True)
            if zmq.zmq_version_info() >= (4, 1, 0):
                self.socket.setsockopt(zmq.ROUTER_HANDOVER, True)
        elif self.socket_type == zmq.REQ:
            self.socket.setsockopt(zmq.RCVTIMEO, int(self.timeout * 1000))
        self.socket.setsockopt(zmq.SNDTIMEO, int(self.timeout * 1000))
        self.socket.setsockopt(zmq.PROBE_ROUTER, probing)
        self.auth_backend.configure()
        self.heartbeat_backend.configure()
        self.initialized = True

    def connect(self, endpoint):
        self._setup_socket(probing=True)
        self.socket.connect(endpoint)

    def bind(self, endpoint):
        self._setup_socket()
        self.socket.bind(endpoint)

    def disconnect(self, endpoint):
        self.socket.disconnect(endpoint)

    def _prepare_work(self, user_id, name, *args, **kw):
        routing_id = self.auth_backend.get_routing_id(user_id)
        work = self.packer.packb((name, args, kw))
        uid = uuid.uuid4().bytes
        message = [routing_id, EMPTY_DELIMITER, VERSION, uid, WORK, work]
        return message, uid

    def create_timeout_detector(self, uuid):
        return self.loop.call_later(
            self.timeout, functools.partial(self.timeout_task, uuid))

    def cleanup_future(self, uuid, future):
        try:
            del self.future_pool[uuid]
        except KeyError:
            pass

    async def on_socket_ready(self, response):
        if len(response) == 4:
            # From REQ socket
            version, message_uuid, message_type = map(bytes, response[:-1])
            message = response[-1]
            routing_id = None
        elif len(response) == 2:
            # PROBING Messages
            routing_id = bytes(response[0])
            version = b''
            message_type = None
            message = response[-1]
        else:
            # from ROUTER socket
            routing_id, delimiter, version, message_uuid, message_type = map(
                bytes, response[:-1])
            message = response[-1]
        try:
            user_id = message.get(b'User-Id').encode('utf-8')
        except zmq.error.ZMQError:
            # no zap handler
            user_id = b''
        else:
            self.auth_backend.register_routing_id(user_id, routing_id)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                'Message received for {}: '
                'meta: {} message: {}'.format(
                    (self.user_id.hex() if self.user_id is not None
                     else user_id.hex()),
                    b''.join(map(bytes, response[:-1])).hex(),
                    pprint.pformat(self.packer.unpackb(response[-1]))
                    if message_type in (WORK, OK, HELLO)
                    else bytes(response[-1]).hex()))
        if message_type is None:
            # PROBING message
            return
        assert version == VERSION
        if not self.auth_backend.is_authenticated(user_id):
            if message_type != HELLO:
                return await self.auth_backend.handle_authentication(
                    user_id, routing_id, message_uuid)
            return await self.auth_backend.handle_hello(
                user_id, routing_id, message_uuid, message)

        await self.heartbeat_backend.handle_heartbeat(user_id, routing_id)
        return await self.dispatch(message_type, message, routing_id, user_id,
                                   message_uuid)

    async def dispatch(self, message_type, message, routing_id, user_id,
                       message_uuid):
        if message_type == WORK:
            return await self._handle_work(
                message, routing_id, user_id, message_uuid)
        if message_type == OK:
            return self._handle_ok(message, message_uuid)
        if message_type == ERROR:
            return self._handle_error(message, message_uuid)
        if message_type == AUTHENTICATED:
            return await self.auth_backend.handle_authenticated(message)
        if message_type == UNAUTHORIZED:
            return await self.auth_backend.handle_authentication(
                user_id, routing_id, message_uuid)
        if message_type == HELLO:
            return self.auth_backend.handle_hello(user_id, routing_id,
                                                  message_uuid, message)
        if message_type == HEARTBEAT:
            # Can ignore, because every message is an heartbeat
            return
        logger.error('Unknown message_type received {!r}'.format(message_type))
        raise NotImplementedError

    def _handle_ok(self, message, message_uuid):
        value = self.packer.unpackb(message)
        logger.debug('Client result {!r} from {!r}'.format(value,
                                                           message_uuid))
        future = self.future_pool.pop(message_uuid)
        future.set_result(value)

    def _handle_error(self, message, message_uuid):
        value = self.packer.unpackb(message)
        future = self.future_pool.pop(message_uuid, DummyFuture())
        klass, message, traceback = value
        full_message = '\n'.join((format_remote_traceback(traceback),
                                  message))
        try:
            exception = getattr(builtins, klass)(full_message)
        except AttributeError:
            if klass in internal_exceptions:
                exception = getattr(interfaces, klass)(full_message)
                future.set_exception(exception)
            else:
                # Not stdlib Exception
                # fallback on something that expose informations received
                # from remote worker
                future.set_exception(Exception('\n'.join((klass,
                                                          full_message))))
        else:
            future.set_exception(exception)

    @property
    def register_rpc(self):
        return functools.partial(register_rpc, registry=self.registry)

    def _make_context(self):
        instance = zmq.asyncio.Context.instance()
        assert isinstance(instance, zmq.asyncio.Context)
        return instance

    async def _handle_work_proxy(self, locator, args, kw, user_id,
                                 message_uuid):
        worker_callable = get_rpc_callable(
            locator,
            registry=self.registry,
            **self.auth_backend.get_predicate_arguments(user_id))
        if worker_callable.with_identity:
            result = worker_callable(user_id, *args, **kw)
        else:
            result = worker_callable(*args, **kw)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    async def _handle_work(self, message, routing_id, user_id, message_uuid):
        locator, args, kw = self.packer.unpackb(message)
        try:
            try:
                result = await self._handle_work_proxy(
                    locator, args, kw, user_id, message_uuid)
            except ServiceNotFoundError:
                if self.proxy_to is None:
                    raise
                result = await self.proxy_to._handle_work_proxy(
                    locator, args, kw, user_id, message_uuid)

        except Exception:
            logger.exception('Pseud job failed')
            exc_type, exc_value = sys.exc_info()[:2]
            traceback_ = traceback.format_exc()
            name = exc_type.__name__
            message = str(exc_value)
            result = (name, message, traceback_)
            status = ERROR
        else:
            status = OK
        response = self.packer.packb(result)
        message = [routing_id, EMPTY_DELIMITER, VERSION, message_uuid, status,
                   response]
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Worker send reply {!r} {}'.format(
                message[:-1],
                pprint.pformat(result))
            )
        await self.send_message(message)

    async def send_work(self, user_id, name, *args, **kw):
        await self.start()
        message, uid = self._prepare_work(user_id, name, *args, **kw)
        self.future_pool[uid] = future = self.loop.create_future()
        future.add_done_callback(functools.partial(self.cleanup_future, uid))
        asyncio.ensure_future(future, loop=self.loop)
        self.create_timeout_detector(uid)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Sending work: {!r} {}'.format(
                message[:-1],
                pprint.pformat(self.packer.unpackb(message[-1]))))
        self.auth_backend.save_last_work(message)
        await self.send_message(message)
        return await future

    async def send_message(self, message):
        try:
            await self.socket.send_multipart(message)
        except zmq.error.ZMQError as exc:
            if exc.errno == zmq.EHOSTUNREACH:
                # ROUTER does not know yet the recipient
                if self.counter[message[0]] > MAX_EHOSTUNREACH_RETRY:
                    return
                self.counter[message[0]] += 1
                # retry in 100 ms
                await asyncio.sleep(.1)
                await self.send_message(message)

    async def start(self):
        if self.reader is None:
            self.reader = self.loop.create_task(
                read_forever(self.socket, self.on_socket_ready))
            self.reader.add_done_callback(handle_result)
        self.counter = Counter()

    def timeout_task(self, uuid):
        try:
            self.future_pool[uuid].set_exception(asyncio.TimeoutError())
        except KeyError:
            pass

    async def stop(self):
        if self.reader is not None:
            self.reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader
            self.reader = None
        if not self.socket.closed:
            self.socket.close(linger=0)
        await asyncio.gather(
            self.auth_backend.stop(),
            self.heartbeat_backend.stop(),
        )

    async def __aenter__(self):
        await self.start()

    async def __aexit__(self, *args):
        await self.stop()
