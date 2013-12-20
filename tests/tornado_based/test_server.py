import os.path
import time

import msgpack
import zmq
from zmq.eventloop import zmqstream
import tornado.testing


def test_server_creation():
    from pseud import Server
    from pseud import auth, heartbeat, predicate  # NOQA
    identity = 'echo'
    server = Server(identity)
    assert server.identity == identity
    assert server.security_plugin == 'noop_auth_backend'


def test_server_can_bind():
    from pseud import Server
    from pseud import auth, heartbeat, predicate  # NOQA
    identity = 'echo'
    endpoint = 'inproc://{}'.format(__name__)
    server = Server(identity,
                    security_plugin='noop_auth_backend')
    server.bind(endpoint)


def test_server_can_connect():
    from pseud import Server
    from pseud import auth, heartbeat, predicate  # NOQA
    identity = 'echo'
    endpoint = 'tcp://127.0.0.1:5000'
    server = Server(identity,
                    security_plugin='noop_auth_backend')
    server.connect(endpoint)


class ServerTestCase(tornado.testing.AsyncTestCase):

    timeout = 2

    def make_one_client_socket(self, identity, endpoint):
        context = zmq.Context.instance()
        req_sock = context.socket(zmq.ROUTER)
        req_sock.identity = identity
        req_sock.connect(endpoint)
        return req_sock

    def make_one_server(self, identity, endpoint):
        from pseud import Server
        from pseud import auth, heartbeat, predicate  # NOQA
        server = Server(identity, io_loop=self.io_loop)
        server.bind(endpoint)
        return server

    @tornado.testing.gen_test
    def test_job_running(self):
        from pseud.interfaces import OK, VERSION, WORK
        from pseud.utils import register_rpc

        identity = 'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__)

        @register_rpc
        def job_success(a, b, c, d=None):
            time.sleep(.2)
            return True

        server = self.make_one_server(identity, endpoint)
        socket = self.make_one_client_socket('client', endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = msgpack.packb((job_success.func_name, (1, 2, 3), {'d': False}))
        yield tornado.gen.Task(stream.send_multipart,
                               [identity, '', VERSION, '', WORK, work])
        yield server.start()
        response = yield tornado.gen.Task(stream.on_recv)
        self.io_loop.add_timeout(self.io_loop.time() + .1,
                                 self.io_loop.stop)
        self.io_loop.start()
        assert response == [identity, '', VERSION, '', OK, msgpack.packb(True)]
        server.stop()

    @tornado.testing.gen_test
    def test_job_not_found(self):
        import pseud
        from pseud.interfaces import ERROR, VERSION, WORK
        identity = 'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__)
        server = self.make_one_server(identity, endpoint)
        socket = self.make_one_client_socket('client', endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = msgpack.packb(('thisIsNotAFunction', (), {}))
        yield server.start()
        yield tornado.gen.Task(stream.send_multipart,
                               [identity, '', VERSION, '', WORK, work])
        response = yield tornado.gen.Task(stream.on_recv)
        self.io_loop.add_timeout(self.io_loop.time() + .1,
                                 self.io_loop.stop)
        self.io_loop.start()
        assert response[:-1] == [identity, '', VERSION, '', ERROR]
        klass, message, traceback = msgpack.unpackb(response[-1])
        assert klass == 'ServiceNotFoundError'
        assert message == 'thisIsNotAFunction'
        # pseud.__file__ might ends with .pyc
        assert os.path.dirname(pseud.__file__) in traceback
        server.stop()

    @tornado.testing.gen_test
    def test_job_raise(self):
        from pseud.interfaces import ERROR, VERSION, WORK
        from pseud.utils import register_rpc

        identity = 'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__)

        @register_rpc
        def job_buggy(*args, **kw):
            raise ValueError('too bad')

        server = self.make_one_server(identity, endpoint)
        socket = self.make_one_client_socket('client', endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = msgpack.packb((job_buggy.func_name, (), {}))
        yield server.start()
        yield tornado.gen.Task(stream.send_multipart,
                               [identity, '', VERSION, '', WORK, work])
        response = yield tornado.gen.Task(stream.on_recv)
        self.io_loop.add_timeout(time.time() + .1, self.stop)
        self.wait()
        assert response[:-1] == [identity, '', VERSION, '', ERROR]
        klass, message, traceback = msgpack.unpackb(response[-1])
        assert klass == 'ValueError'
        assert message == 'too bad'
        assert __file__ in traceback
        server.stop()
