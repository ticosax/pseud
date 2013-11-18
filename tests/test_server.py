import time

import msgpack
import zmq
from zmq.eventloop import zmqstream
import tornado.testing


def test_server_creation():
    from pyzmq_rpc import Server
    identity = 'echo'
    context_module_name = __name__
    server = Server(identity, context_module_name)
    assert server.identity == identity
    assert server.context_module_name == context_module_name


def test_server_can_bind():
    from pyzmq_rpc import Server
    identity = 'echo'
    context_module_name = __name__
    endpoint = 'ipc://{}'.format(__name__)
    server = Server(identity, context_module_name)
    server.bind(endpoint)


def test_server_can_connect():
    from pyzmq_rpc import Server
    identity = 'echo'
    context_module_name = __name__
    endpoint = 'tcp://127.0.0.1:5000'
    server = Server(identity, context_module_name)
    server.connect(endpoint)


def job_success(a, b, c, d=None):
    time.sleep(1)
    return True


def job_buggy(*args, **kw):
    raise ValueError('too bad')


class ServerTestCase(tornado.testing.AsyncTestCase):

    timeout = 2

    def make_one_client_socket(self, identity, endpoint):
        context = zmq.Context.instance()
        req_sock = context.socket(zmq.ROUTER)
        req_sock.identity = identity
        req_sock.connect(endpoint)
        return req_sock

    def make_one_server(self, identity, context_module_name, endpoint):
        from pyzmq_rpc import Server
        server = Server(identity, context_module_name, io_loop=self.io_loop)
        server.bind(endpoint)
        server.start()
        return server

    @tornado.testing.gen_test
    def test_job_running(self):
        from pyzmq_rpc import OK, VERSION, WORK
        identity = 'echo'
        context_module_name = __name__
        endpoint = 'ipc://{}'.format(self.__class__.__name__)
        self.make_one_server(identity, context_module_name, endpoint)
        socket = self.make_one_client_socket('client', endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = msgpack.packb((job_success.func_name, (1, 2, 3), {'d': False}))
        yield tornado.gen.Task(stream.send_multipart,
                               [identity, VERSION, '', WORK, work])
        response = yield tornado.gen.Task(stream.on_recv)
        self.io_loop.add_timeout(self.io_loop.time() + .1,
                                 self.io_loop.stop)
        print ' before looping'
        self.io_loop.start()
        assert response == [identity, VERSION, '', OK, msgpack.packb(True)]

    @tornado.testing.gen_test
    def test_job_not_found(self):
        import pyzmq_rpc
        from pyzmq_rpc import ERROR, VERSION, WORK
        identity = 'echo'
        context_module_name = __name__
        endpoint = 'ipc://{}'.format(self.__class__.__name__)
        self.make_one_server(identity, context_module_name, endpoint)
        socket = self.make_one_client_socket('client', endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = msgpack.packb(('thisIsNotAFunction', (), {}))
        yield tornado.gen.Task(stream.send_multipart,
                               [identity, VERSION, '', WORK, work])
        response = yield tornado.gen.Task(stream.on_recv)
        self.io_loop.add_timeout(self.io_loop.time() + .1,
                                 self.io_loop.stop)
        self.io_loop.start()
        assert response[:-1] == [identity, VERSION, '', ERROR]
        klass, message, traceback = msgpack.unpackb(response[-1])
        assert klass == 'ServiceNotFoundError'
        assert message == 'thisIsNotAFunction'
        # pyzmq_rpc.__file__ might ends with .pyc
        assert any((pyzmq_rpc.__file__ in traceback,
                    pyzmq_rpc.__file__[:-1] in traceback))

    @tornado.testing.gen_test
    def test_job_raise(self):
        from pyzmq_rpc import ERROR, VERSION, WORK
        identity = 'echo'
        context_module_name = __name__
        endpoint = 'ipc://{}'.format(self.__class__.__name__)
        self.make_one_server(identity, context_module_name, endpoint)
        socket = self.make_one_client_socket('client', endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = msgpack.packb((job_buggy.func_name, (), {}))
        yield tornado.gen.Task(stream.send_multipart,
                               [identity, VERSION, '', WORK, work])
        response = yield tornado.gen.Task(stream.on_recv)
        self.io_loop.add_timeout(time.time() + .1, self.stop)
        self.wait()
        assert response[:-1] == [identity, VERSION, '', ERROR]
        klass, message, traceback = msgpack.unpackb(response[-1])
        assert klass == 'ValueError'
        assert message == 'too bad'
        assert __file__ in traceback
