from __future__ import unicode_literals
import functools
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
    user_id = b'echo'
    server = Server(user_id)
    assert server.user_id == user_id
    assert server.security_plugin == 'noop_auth_backend'


def test_server_can_bind():
    from pseud import Server
    user_id = b'echo'
    endpoint = 'inproc://{}'.format(__name__).encode()
    server = Server(user_id,
                    security_plugin='noop_auth_backend')
    server.bind(endpoint)


def test_server_can_connect():
    from pseud import Server
    user_id = b'echo'
    endpoint = b'tcp://127.0.0.1:5000'
    server = Server(user_id,
                    security_plugin='noop_auth_backend')
    server.connect(endpoint)


def test_server_with_its_loop_instance():
    from pseud import SyncClient, Server
    endpoint = b'ipc:///tmp/test_socket'

    def start_server(can_stop):
        server = Server(b'a')
        server.bind(endpoint)
        server.register_rpc(str.lower)

        def stop_server(server, can_stop):
            can_stop.wait()
            server.stop()

        stop_thread = threading.Thread(
            target=stop_server,
            args=(server, can_stop))

        stop_thread.start()
        server.start()

    can_stop = threading.Event()
    server_thread = threading.Thread(
        target=start_server,
        args=(can_stop,))
    server_thread.start()

    client = SyncClient()
    client.connect(endpoint)
    result = client.lower('TOTO')
    can_stop.set()
    assert result == 'toto'


class ServerTestCase(tornado.testing.AsyncTestCase):

    timeout = 2

    def make_one_client_socket(self, endpoint):
        context = zmq.Context.instance()
        req_sock = context.socket(zmq.ROUTER)
        req_sock.connect(endpoint)
        return req_sock

    def make_one_server(self, user_id, endpoint):
        from pseud import Server
        server = Server(user_id, io_loop=self.io_loop)
        server.bind(endpoint)
        return server

    @tornado.testing.gen_test
    def test_job_running(self):
        from pseud.interfaces import EMPTY_DELIMITER, OK, VERSION, WORK
        from pseud.packer import Packer
        from pseud.utils import register_rpc

        user_id = b'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__).encode()

        @register_rpc
        def job_success(a, b, c, d=None):
            time.sleep(.2)
            return True

        server = self.make_one_server(user_id, endpoint)
        socket = self.make_one_client_socket(endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = Packer().packb(('job_success', (1, 2, 3), {'d': False}))
        yield tornado.gen.Task(stream.send_multipart,
                               [user_id, EMPTY_DELIMITER, VERSION, b'',
                                WORK, work])
        yield server.start()
        response = yield tornado.gen.Task(stream.on_recv)
        assert response == [user_id, EMPTY_DELIMITER, VERSION, b'',
                            OK, Packer().packb(True)]
        server.stop()

    @tornado.testing.gen_test
    def test_job_not_found(self):
        import pseud
        from pseud.interfaces import EMPTY_DELIMITER, ERROR, VERSION, WORK
        from pseud.packer import Packer
        user_id = b'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__).encode()
        server = self.make_one_server(user_id, endpoint)
        socket = self.make_one_client_socket(endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = Packer().packb(('thisIsNotAFunction', (), {}))
        yield server.start()
        yield tornado.gen.Task(stream.send_multipart,
                               [user_id, EMPTY_DELIMITER, VERSION, b'', WORK,
                                work])
        response = yield tornado.gen.Task(stream.on_recv)
        assert response[:-1] == [user_id, EMPTY_DELIMITER, VERSION, b'',
                                 ERROR]
        klass, message, traceback = Packer().unpackb(response[-1])
        assert klass == 'ServiceNotFoundError'
        assert message == 'thisIsNotAFunction'
        # pseud.__file__ might ends with .pyc
        assert os.path.dirname(pseud.__file__) in traceback
        server.stop()

    @tornado.testing.gen_test
    def test_job_raise(self):
        from pseud.interfaces import ERROR, VERSION, WORK
        from pseud.packer import Packer
        from pseud.utils import register_rpc

        user_id = b'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__).encode()

        @register_rpc
        def job_buggy(*args, **kw):
            raise ValueError('too bad')

        server = self.make_one_server(user_id, endpoint)
        socket = self.make_one_client_socket(endpoint)
        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        work = Packer().packb(('job_buggy', (), {}))
        yield server.start()
        yield tornado.gen.Task(stream.send_multipart,
                               [user_id, b'', VERSION, b'', WORK, work])
        response = yield tornado.gen.Task(stream.on_recv)
        assert response[:-1] == [user_id, b'', VERSION, b'', ERROR]
        klass, message, traceback = Packer().unpackb(response[-1])
        assert klass == 'ValueError'
        assert message == 'too bad'
        assert __file__ in traceback
        server.stop()
