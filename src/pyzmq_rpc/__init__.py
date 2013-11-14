"""
RPC implementation on top of MDP protocol v1
http://rfc.zeromq.org/spec:7
"""
import importlib
import __builtin__
import sys
import textwrap
import traceback
import uuid

import msgpack
import zmq
from zmq.eventloop import ioloop, zmqstream

from .interfaces import TimeoutError


ioloop.install()

_marker = object()

OK = '\x01'
HELLO = '\x02'
WORK = '\x03'
ERROR = '\x12'

VERSION = 'v1'


class ObjectifyDict(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Service(object):
    def __init__(self, endpoint, identity, context=None,
                 context_module_name=None):
        self.context = context or zmq.Context.instance()
        self.context_module_name = context_module_name

    def run(self):
        while True:
            request = self.socket.recv_multipart()
            assert len(request) == 1
            full_message = msgpack.unpackb(request[0])
            protocol, identity, locator, args, kw = full_message
            assert protocol == 'v1'
            if '.' in locator:
                splitted = locator.split('.')
                module_path, function_name = splitted[:-1], splitted[-1]
                context_module = importlib.import_module(*module_path)
            elif self.context:
                context_module = sys.modules[self.context]
                function_name = locator
            else:
                context_module = ObjectifyDict(**globals())
                function_name = locator

            worker_callable = getattr(context_module, function_name)
            try:
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
            reply = [status, msgpack.packb(result)]
            self.socket.send_multipart(reply)


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
        if name.startswith('_') or name in self.__dict__:
            if default is _marker:
                return super(AttributeWrapper, self).__getattr__(name, default)
            return super(AttributeWrapper, self).__getattr__(name)
        self.name = name
        return self

    def name_getter(self):
        return '.'.join(self._part_names)

    def name_setter(self, value):
        self._part_names.append(value)

    name = property(name_getter, name_setter)

    def __call__(self, *args, **kw):
        return self.client._send_work(self.name, *args, **kw)


class BaseRPC(object):
    def _make_socket(self):
        socket = self._context.socket(self._socket_type)
        socket.identity = self._identity
        if self._timeout:
            socket.rcvtimeo = self._timeout
        return socket

    def connect(self, endpoint):
        self._socket = self._make_socket()
        self._socket.connect(endpoint)
        self._initialized = True

    def bind(self, endpoint):
        self._socket = self._make_socket()
        self._socket.bind(endpoint)
        self._initialized = True


class Client(BaseRPC):
    _socket_type = zmq.REQ

    def __init__(self, identity, server_identity,
                 context=None, timeout=5):
        self._context = context or zmq.Context.instance()
        self._identity = identity
        self._server_identity = server_identity
        self._timeout = timeout * 1000
        self._initialized = False

    def __getattr__(self, name, default=_marker):
        if name.startswith('_') or name in self.__dict__:
            if default is _marker:
                return super(Client, self).__getattr__(name, default)
            return super(Client, self).__getattr__(name)
        if not self._initialized:
            raise TypeError('You must connect or bind first')
        return AttributeWrapper(self, name)

    def _send_work(self, name, *args, **kw):
        work = msgpack.packb((name, args, kw))
        uid = uuid.uuid4().bytes
        message = [self._server_identity, VERSION, uid, WORK, work]
        print 'sending work', message
        self._socket.send_multipart(message)
        try:
            response = self._socket.recv_multipart()
        except zmq.error.Again:
            raise TimeoutError
        _, version, message_uuid, message_type, value = response
        value = msgpack.unpackb(value)
        if message_type == ERROR:
            klass, message, traceback = value
            full_message = '\n'.join((format_remote_traceback(traceback),
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
            return value
        else:
            raise NotImplementedError


class Server(BaseRPC):
    _socket_type = zmq.ROUTER

    def __init__(self, identity, context_module_name,
                 context=None, io_loop=None, timeout=5):
        self._identity = identity
        self._context_module_name = context_module_name
        self._context = context or zmq.Context.instance()
        self._internal_loop = False
        self._timeout = timeout * 1000
        if io_loop is None:
            self._internal_loop = True
            self._io_loop = ioloop.IOLoop.instance()
        else:
            self._io_loop = io_loop

    def start(self):
        self.stream = zmqstream.ZMQStream(self._socket)
        self.stream.on_recv(self.handle_response)
        if self._internal_loop:
            print 'Worker ready'
            self._io_loop.start()

    def handle_response(self, response):
        print 'Worker received', response
        if len(response) == 7:
            zid, _, peer_id, version, message_uuid, message_type, message =\
                response
        else:
            zid = None
            peer_id, version, message_uuid, message_type, message = response
        assert version == VERSION
        if message_type == HELLO:
            print 'new client {}'.format(message)
            self.socket.send_multipart([message, message_uuid, OK, 'Welcome'])
        elif message_type == WORK:
            locator, args, kw = msgpack.unpackb(message)
            if '.' in locator:
                splitted = locator.split('.')
                module_path, function_name = splitted[:-1], splitted[-1]
                context_module = importlib.import_module(*module_path)
            elif self._context_module_name:
                context_module = sys.modules[self._context_module_name]
                function_name = locator
            else:
                raise NotImplementedError

            worker_callable = getattr(context_module, function_name)
            try:
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
            self._socket.send_multipart(message)
        elif message_type == OK:
            print 'Client result {} from {}'.format(message, message_uuid)
        else:
            print repr(message_type)
            raise NotImplementedError
