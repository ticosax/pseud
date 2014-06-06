from __future__ import unicode_literals
import os.path
import threading
import time

from future.builtins import str
import zmq
from zmq.eventloop import ioloop, zmqstream
import tornado.testing


ioloop.install()


def test_server_creation():
    from pseud import Server
    identity = b'echo'
    server = Server(identity)
    assert server.identity == identity
    assert server.security_plugin == 'noop_auth_backend'


def test_server_can_bind():
    from pseud import Server
    identity = b'echo'
    endpoint = 'inproc://{}'.format(__name__).encode()
    server = Server(identity,
                    security_plugin='noop_auth_backend')
    server.bind(endpoint)


def test_server_can_connect():
    from pseud import Server
    identity = b'echo'
    endpoint = b'tcp://127.0.0.1:5000'
    server = Server(identity,
                    security_plugin='noop_auth_backend')
    server.connect(endpoint)


def test_server_with_its_loop_instance():
    from pseud import SyncClient, Server
    endpoint = b'ipc:///tmp/test_socket'

    def start_server():
        server = Server(b'a')
        server.bind(endpoint)
        server.register_rpc(str.lower)
        server.io_loop.add_timeout(server.io_loop.time() + .2,
                                   server.stop)
        server.start()

    server_thread = threading.Thread(target=start_server)
    server_thread.start()

    client = SyncClient()
    client.connect(endpoint)
    result = client.lower('TOTO')
    assert result == 'toto'


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
        server = Server(identity, io_loop=self.io_loop)
        server.bind(endpoint)
        return server

    @tornado.testing.gen_test
    def test_job_running(self):
        from pseud.common import msgpack_packb
        from pseud.interfaces import EMPTY_DELIMITER, OK, VERSION, WORK
        from pseud.utils import register_rpc

        identity = b'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__).encode()

        @register_rpc
        def job_success(a, b, c, d=None):
            time.sleep(.2)
            return True

        server = self.make_one_server(identity, endpoint)
        socket = self.make_one_client_socket(b'client', endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = msgpack_packb(('job_success', (1, 2, 3), {'d': False}))
        yield tornado.gen.Task(stream.send_multipart,
                               [identity, EMPTY_DELIMITER, VERSION, b'',
                                WORK, work])
        yield server.start()
        response = yield tornado.gen.Task(stream.on_recv)
        assert response == [identity, EMPTY_DELIMITER, VERSION, b'',
                            OK, msgpack_packb(True)]
        server.stop()

    @tornado.testing.gen_test
    def test_job_not_found(self):
        import pseud
        from pseud.common import msgpack_packb, msgpack_unpackb
        from pseud.interfaces import EMPTY_DELIMITER, ERROR, VERSION, WORK
        identity = b'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__).encode()
        server = self.make_one_server(identity, endpoint)
        socket = self.make_one_client_socket(b'client', endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = msgpack_packb(('thisIsNotAFunction', (), {}))
        yield server.start()
        yield tornado.gen.Task(stream.send_multipart,
                               [identity, EMPTY_DELIMITER, VERSION, b'', WORK,
                                work])
        response = yield tornado.gen.Task(stream.on_recv)
        assert response[:-1] == [identity, EMPTY_DELIMITER, VERSION, b'',
                                 ERROR]
        klass, message, traceback = msgpack_unpackb(response[-1])
        assert klass == 'ServiceNotFoundError'
        assert message == 'thisIsNotAFunction'
        # pseud.__file__ might ends with .pyc
        assert os.path.dirname(pseud.__file__) in traceback
        server.stop()

    @tornado.testing.gen_test
    def test_job_raise(self):
        from pseud.common import msgpack_packb, msgpack_unpackb
        from pseud.interfaces import ERROR, VERSION, WORK
        from pseud.utils import register_rpc

        identity = b'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__).encode()

        @register_rpc
        def job_buggy(*args, **kw):
            raise ValueError('too bad')

        server = self.make_one_server(identity, endpoint)
        socket = self.make_one_client_socket(b'client', endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = msgpack_packb(('job_buggy', (), {}))
        yield server.start()
        yield tornado.gen.Task(stream.send_multipart,
                               [identity, b'', VERSION, b'', WORK, work])
        response = yield tornado.gen.Task(stream.on_recv)
        assert response[:-1] == [identity, b'', VERSION, b'', ERROR]
        klass, message, traceback = msgpack_unpackb(response[-1])
        assert klass == 'ValueError'
        assert message == 'too bad'
        assert __file__ in traceback
        server.stop()
