import __builtin__
import importlib
import functools
import operator
import sys
import textwrap
import traceback
import uuid

import msgpack
import zope.component
import zope.interface

from .interfaces import (AUTHENTICATED,
                         ERROR,
                         HEARTBEAT,
                         HELLO,
                         IAuthenticationBackend,
                         IHeartbeatBackend,
                         OK,
                         ServiceNotFoundError,
                         UNAUTHORIZED,
                         VERSION,
                         WORK,
                         )

_marker = object()


def format_remote_traceback(traceback):
    pivot = '\n{}'.format(3 * 4 * ' ')  # like three tabs
    return textwrap.dedent("""
        -- Beginning of remote traceback --
            {}
        -- End of remote traceback --
        """.format(pivot.join(traceback.splitlines())))


class AttributeWrapper(object):
    def __init__(self, rpc, name):
        self.rpc = rpc
        self._part_names = name.split('.')

    def __getattr__(self, name, default=_marker):
        try:
            if default is _marker:
                return super(AttributeWrapper, self).__getattr__(name)
            return super(AttributeWrapper, self).__getattr__(name,
                                                             default=default)
        except AttributeError:
            self.name = name
            return self

    def name_getter(self):
        return '.'.join(self._part_names)

    def name_setter(self, value):
        self._part_names.append(value)

    name = property(name_getter, name_setter)

    def __call__(self, *args, **kw):
        return self.rpc.send_work(self.rpc.peer_identity, self.name,
                                  *args, **kw)


class BaseRPC(object):
    def __init__(self, identity, peer_identity=None,
                 context_module_name=None, context=None, io_loop=None,
                 security_plugin='noop_auth_backend',
                 public_key=None, private_key=None,
                 peer_public_key=None, timeout=5,
                 password=None,
                 heartbeat_plugin='noop_heartbeat_backend'):
        self.identity = identity
        self.context_module_name = context_module_name
        self.context = context or self._make_context()
        self.peer_identity = peer_identity
        self.security_plugin = security_plugin
        self.future_pool = {}
        self.initialized = False
        self.auth_backend = zope.component.getAdapter(self,
                                                      IAuthenticationBackend,
                                                      name=self.security_plugin
                                                      )
        self.public_key = public_key
        self.private_key = private_key
        self.peer_public_key = peer_public_key
        self.password = password
        self.heartbeat_backend = zope.component.getAdapter(
            self,
            IHeartbeatBackend,
            name=heartbeat_plugin)
        self._backend_init(io_loop=io_loop)

    def __getattr__(self, name, default=_marker):
        if name in ('connect', 'bind'):
            return functools.partial(self.connect_or_bind, name)
        try:
            if default is _marker:
                return super(BaseRPC, self).__getattr__(name)
            return super(BaseRPC, self).__getattr__(name, default=default)
        except AttributeError:
            if not self.initialized:
                raise RuntimeError('You must connect or bind first'
                                   ' in order to call {!r}'.format(name))
            return AttributeWrapper(self, name)

    def connect_or_bind(self, name, endpoint):
        socket = self.context.socket(self.socket_type)
        self.socket = socket
        socket.identity = self.identity
        # socket.linger = 0
        socket.ROUTER_MANDATORY = True
        self.auth_backend.configure()
        self.heartbeat_backend.configure()
        caller = operator.methodcaller(name, endpoint)
        caller(socket)
        self.initialized = True

    def _prepare_work(self, peer_identity, name, *args, **kw):
        work = msgpack.packb((name, args, kw))
        uid = uuid.uuid4().bytes
        message = [peer_identity, VERSION, uid, WORK, work]
        return message, uid

    def on_socket_ready(self, response):
        print 'Message received for {}'.format(self), response
        # When client uses ROUTER socket
        peer_id, version, message_uuid, message_type, message = response
        assert version == VERSION
        if not self.auth_backend.is_authenticated(peer_id):
            if message_type != HELLO:
                self.auth_backend.handle_authentication(peer_id, message_uuid)
            else:
                self.auth_backend.handle_hello(peer_id, message_uuid,
                                               message)
        else:
            self.heartbeat_backend.handle_heartbeat(peer_id)
            if message_type == WORK:
                self._handle_work(message, peer_id, message_uuid)
            elif message_type == OK:
                self._handle_ok(message, message_uuid)
            elif message_type == ERROR:
                self._handle_error(message, message_uuid)
            elif message_type == AUTHENTICATED:
                self.auth_backend.handle_authenticated(message)
            elif message_type == UNAUTHORIZED:
                self.auth_backend.handle_authentication(peer_id, message_uuid)
            elif message_type == HELLO:
                self.auth_backend.handle_hello(peer_id, message_uuid, message)
            elif message_type == HEARTBEAT:
                # Can ignore, because every message is an heartbeat
                pass
            else:
                print repr(message_type)
                raise NotImplementedError

    def _handle_work(self, message, peer_id, message_uuid):
        # TODO provide sandboxing to disallow
        # untrusted user to call any module
        locator, args, kw = msgpack.unpackb(message)
        if '.' in locator:
            splitted = locator.split('.')
            module_path, function_name = splitted[:-1], splitted[-1]
            context_module = importlib.import_module(*module_path)
        elif self.context_module_name:
            context_module = sys.modules[self.context_module_name]
            function_name = locator
        else:
            raise NotImplementedError
        try:
            try:
                worker_callable = getattr(context_module, function_name)
            except AttributeError:
                raise ServiceNotFoundError(locator)
            result = worker_callable(*args, **kw)
        except Exception:
            exc_type, exc_value = sys.exc_info()[:2]
            traceback_ = traceback.format_exc()
            name = exc_type.__name__
            message = str(exc_value)
            result = (name, message, traceback_)
            status = ERROR
        else:
            status = OK
        response = msgpack.packb(result)
        message = [peer_id, VERSION, message_uuid, status, response]
        print 'worker send reply', message
        self.send_message(message)

    def _handle_ok(self, message, message_uuid):
        value = msgpack.unpackb(message)
        print 'Client result {!r} from {!r}'.format(value, message_uuid)
        future = self.future_pool.pop(message_uuid)
        self._store_result_in_future(future, value)

    def _handle_error(self, message, message_uuid):
        value = msgpack.unpackb(message)
        future = self.future_pool.pop(message_uuid)
        klass, message, trace_back = value
        full_message = '\n'.join((format_remote_traceback(trace_back),
                                  message))
        try:
            exception = getattr(__builtin__, klass)(full_message)
        except AttributeError:
            # Not stdlib Exception
            # fallback on something that expose informations received
            # from remote worker
            future.set_exception(Exception('\n'.join((klass, full_message))))
        else:
            future.set_exception(exception)
