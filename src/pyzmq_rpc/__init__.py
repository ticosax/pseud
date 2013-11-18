"""
RPC implementation on top of MDP protocol v1
http://rfc.zeromq.org/spec:7
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
import toro
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
    def __init__(self, client, name):
        self.client = client
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
        return self.client._send_work(self.name, *args, **kw)


class BaseRPC(object):
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
        if default is _marker:
            return super(BaseRPC, self).__getattr__(name)
        return super(BaseRPC, self).__getattr__(name, default=default)

    def connect_or_bind(self, name, endpoint):
        self.socket = self._make_socket()
        caller = operator.methodcaller(name, endpoint)
        caller(self.socket)
        self.stream = zmqstream.ZMQStream(self.socket, self.io_loop)
        self.initialized = True

    @tornado.gen.coroutine
    def stop(self):
        self.stream.flush()
        self.stream.close()
        if self.internal_loop:
            self.io_loop.stop()


class Client(BaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, identity, server_identity,
                 context=None, io_loop=None, timeout=5):
        self.context = context or zmq.Context.instance()
        self.identity = identity
        self.server_identity = server_identity
        self.timeout = timeout
        self.initialized = False
        self.internal_loop = False
        self.timeout_condition = toro.Condition()
        if io_loop is None:
            self.internal_loop = True
            self.io_loop = ioloop.IOLoop.instance()
        else:
            self.io_loop = io_loop

    def __getattr__(self, name, default=_marker):
        try:
            if default is _marker:
                return super(Client, self).__getattr__(name)
            return super(Client, self).__getattr__(name, default=default)
        except AttributeError:
            if not self.initialized:
                raise RuntimeError('You must connect or bind first')
            return AttributeWrapper(self, name)

    @tornado.gen.coroutine
    def _send_work(self, name, *args, **kw):
        work = msgpack.packb((name, args, kw))
        uid = uuid.uuid4().bytes
        message = [self.server_identity, VERSION, uid, WORK, work]
        print 'sending work', message
        yield tornado.gen.Task(self.stream.send_multipart, message)
        print 'work sent'
        print 'client waiting for worker response'
        response = yield tornado.gen.Task(self.stream.on_recv)
        print 'finish waiting'
        print 'client got response for work'
        self.stream.stop_on_recv()
        _, version, message_uuid, message_type, value = response
        value = msgpack.unpackb(value)
        if message_type == ERROR:
            klass, message, trace_back = value
            full_message = '\n'.join((format_remote_traceback(trace_back),
                                      message))
            try:
                exception = getattr(__builtin__, klass)(full_message)
            except AttributeError:
                # Not stdlib Exception
                # fallback on something that expose informations received
                # from remote worker
                raise Exception('\n'.join((klass, full_message)))
            raise exception
        elif message_type == OK:
            raise tornado.gen.Return(value)
        else:
            raise NotImplementedError


class Server(BaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, identity, context_module_name,
                 context=None, io_loop=None, timeout=5):
        self.identity = identity
        self.context_module_name = context_module_name
        self.context = context or zmq.Context.instance()
        self.internal_loop = False
        self.timeout = timeout * 1000
        if io_loop is None:
            self.internal_loop = True
            self.io_loop = ioloop.IOLoop.instance()
        else:
            self.io_loop = io_loop

    @tornado.gen.coroutine
    def start(self):
        while True:
            response = yield tornado.gen.Task(self.stream.on_recv)
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
                print 'new client {}'.format(message)
                self.socket.send_multipart([message, message_uuid, OK,
                                            'Welcome'])
            elif message_type == WORK:
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
                        worker_callable = getattr(context_module,
                                                  function_name)
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
                yield tornado.gen.Task(self.stream.send_multipart, message)
            elif message_type == OK:
                print 'Client result {} from {}'.format(message, message_uuid)
            else:
                print repr(message_type)
                raise NotImplementedError
            if self.internal_loop:
                print self.__class__.__name__, 'ready'
                self.io_loop.start()
