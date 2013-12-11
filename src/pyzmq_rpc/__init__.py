"""
"""
import importlib
import __builtin__
import functools
import operator
import sys
import textwrap
import traceback
import uuid

import msgpack
import tornado.concurrent
import tornado.gen
import zmq
from zmq.eventloop import ioloop, zmqstream

from .interfaces import ServiceNotFoundError


ioloop.install()

_marker = object()

OK = '\x01'
HELLO = '\x02'
WORK = '\x03'
ERROR = '\x12'

VERSION = 'v1'


def format_remote_traceback(traceback):
    indent = 3 * 4 * ' '
    pivot = '\n{}'.format(indent)
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

    @tornado.gen.coroutine
    def __call__(self, *args, **kw):
        return self.rpc._send_work(self.rpc.peer_identity, self.name,
                                   *args, **kw)


class BaseRPC(object):
    def __init__(self, identity, peer_identity=None,
                 context_module_name=None,
                 context=None, io_loop=None, timeout=5):
        self.identity = identity
        self.context_module_name = context_module_name
        self.context = context or zmq.Context.instance()
        self.internal_loop = False
        self.timeout = timeout * 1000
        self.peer_identity = peer_identity
        self.future_pool = {}
        self.initialized = False
        if io_loop is None:
            self.internal_loop = True
            self.io_loop = ioloop.IOLoop.instance()
        else:
            self.io_loop = io_loop

    def _make_socket(self):
        socket = self.context.socket(self.socket_type)
        socket.identity = self.identity
        # if self.timeout:
        #     socket.rcvtimeo = self.timeout * 1000
        socket.linger = 0
        return socket

    def __getattr__(self, name, default=_marker):
        if name in ('connect', 'bind'):
            return functools.partial(self.connect_or_bind, name)
        try:
            if default is _marker:
                return super(BaseRPC, self).__getattr__(name)
            return super(BaseRPC, self).__getattr__(name, default=default)
        except AttributeError:
            if not self.initialized:
                raise RuntimeError('You must connect or bind first')
            return AttributeWrapper(self, name)

    def connect_or_bind(self, name, endpoint):
        self.socket = self._make_socket()
        caller = operator.methodcaller(name, endpoint)
        caller(self.socket)
        self.stream = zmqstream.ZMQStream(self.socket, self.io_loop)
        self.initialized = True

    @tornado.gen.coroutine
    def _send_work(self, peer_identity, name, *args, **kw):
        work = msgpack.packb((name, args, kw))
        uid = uuid.uuid4().bytes
        message = [peer_identity, VERSION, uid, WORK, work]
        print 'sending work', message
        yield tornado.gen.Task(self.stream.send_multipart, message)
        print 'work sent'
        # XXX make sure we destroy the future if no answer is comming
        self.future_pool[uid] = future = tornado.concurrent.Future()
        yield self.start()
        raise tornado.gen.Return(future)

    def on_socket_ready(self, response):
        print 'Worker received', response
        if len(response) == 7:
            # When client uses REQ socket
            zid, _, peer_id, version, message_uuid, message_type,\
                message = response
        else:
            # When client uses ROUTER socket
            zid = None
            peer_id, version, message_uuid, message_type, message =\
                response
        assert version == VERSION
        if message_type == HELLO:
            self._handle_hello(message, message_uuid)
        elif message_type == WORK:
            self._handle_work(message, zid, peer_id, message_uuid)
        elif message_type == OK:
            self._handle_ok(message, message_uuid)
        elif message_type == ERROR:
            self._handle_error(message, message_uuid)
        else:
            print repr(message_type)
            raise NotImplementedError

    @tornado.gen.coroutine
    def start(self):
        self.stream.on_recv(self.on_socket_ready)
        if self.internal_loop:
            print self.__class__.__name__, 'ready'
            self.io_loop.start()

    def _handle_hello(self, message, message_uuid):
        print 'new client {}'.format(message)
        self.socket.send_multipart([message, message_uuid, OK,
                                    'Welcome'])

    def _handle_work(self, message, zid, peer_id, message_uuid):
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
        if zid:
            message.insert(0, '')
            message.insert(0, zid)
        print 'worker send reply', message
        self.stream.send_multipart(message)

    def _handle_ok(self, message, message_uuid):
        value = msgpack.unpackb(message)
        print 'Client result {!r} from {!r}'.format(value, message_uuid)
        future = self.future_pool.pop(message_uuid)
        future.set_result(value)

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

    @tornado.gen.coroutine
    def stop(self):
        self.stream.flush()
        self.stream.close()
        if self.internal_loop:
            self.io_loop.stop()


class Client(BaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, identity, peer_identity, context_module_name=None,
                 context=None, io_loop=None, timeout=5):
        super(Client, self).__init__(identity, peer_identity=peer_identity,
                                     context_module_name=context_module_name,
                                     context=context, io_loop=io_loop,
                                     timeout=timeout)


class Server(BaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, identity, context_module_name=None,
                 context=None, io_loop=None, timeout=5):
        super(Server, self).__init__(identity,
                                     context_module_name=context_module_name,
                                     context=context, io_loop=io_loop,
                                     timeout=timeout)

    def __enter__(self, peer_identity):
        self.peer_identity = peer_identity

    def __exit__(self, args):
        self.peer_identity = None
