from concurrent.futures import TimeoutError
import pytest
import tornado.testing
import zmq
from zmq.utils import z85
from zope.interface.verify import verifyClass


def test_noop_auth_backend_client():
    from pyzmq_rpc.auth import NoOpAuthenticationBackendForClient
    from pyzmq_rpc.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend,
                       NoOpAuthenticationBackendForClient)


def test_noop_auth_backend_server():
    from pyzmq_rpc.auth import NoOpAuthenticationBackendForServer
    from pyzmq_rpc.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend,
                       NoOpAuthenticationBackendForServer)


def test_trusted_curve_client():
    from pyzmq_rpc.auth import CurveWithTrustedKeyForClient
    from pyzmq_rpc.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend, CurveWithTrustedKeyForClient)


def test_trusted_curve_server():
    from pyzmq_rpc.auth import CurveWithTrustedKeyForServer
    from pyzmq_rpc.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend, CurveWithTrustedKeyForServer)


def test_untrusted_curve_client():
    from pyzmq_rpc.auth import CurveWithUntrustedKeyForClient
    from pyzmq_rpc.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend, CurveWithUntrustedKeyForClient)


def test_untrusted_curve_server():
    from pyzmq_rpc.auth import CurveWithUntrustedKeyForServer
    from pyzmq_rpc.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend, CurveWithUntrustedKeyForServer)


class CurveTestCase(tornado.testing.AsyncTestCase):
    timeout = 2

    @tornado.testing.gen_test
    def test_trusted_curve(self):
        from pyzmq_rpc import Client, Server
        client_id = 'client'
        server_id = 'server'
        endpoint = 'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'trusted_curve'
        client = Client(client_id, server_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        private_key=client_secret,
                        peer_public_key=server_public,
                        io_loop=self.io_loop)

        server = Server(server_id, security_plugin=security_plugin,
                        public_key=server_public,
                        private_key=server_secret,
                        io_loop=self.io_loop)

        server.bind(endpoint)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        yield server.start()
        yield client.start()
        future = yield client.string.lower('FOO')
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        assert future.result(timeout=self.timeout) == 'foo'
        yield server.stop()
        yield client.stop()

    @tornado.testing.gen_test
    def test_trusted_curve_with_wrong_peer_public_key(self):
        from pyzmq_rpc import Client, Server
        client_id = 'client'
        server_id = 'server'
        endpoint = 'inproc://{}'.format(__name__)
        endpoint = 'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        client = Client(client_id, server_id,
                        security_plugin='trusted_curve',
                        public_key=client_public,
                        private_key=client_secret,
                        peer_public_key=z85.encode('R' * 32),
                        io_loop=self.io_loop)

        server = Server(server_id, security_plugin='trusted_curve',
                        public_key=server_public,
                        private_key=server_secret,
                        io_loop=self.io_loop)

        server.bind(endpoint)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        yield server.start()
        yield client.start()
        future = yield client.string.lower('BAR')
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        with pytest.raises(TimeoutError):
            future.result(timeout=self.timeout)
        yield server.stop()
        yield client.stop()

    @tornado.testing.gen_test()
    def test_untrusted_curve_with_allowed_password(self):
        from pyzmq_rpc import Client, Server

        client_id = 'john'
        server_id = 'server'
        endpoint = 'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'untrusted_curve'
        password = 's3cret!'

        client = Client(client_id, server_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        private_key=client_secret,
                        peer_public_key=server_public,
                        password=password,
                        io_loop=self.io_loop)

        server = Server(server_id,
                        security_plugin=security_plugin,
                        public_key=server_public,
                        private_key=server_secret,
                        io_loop=self.io_loop)

        server.bind(endpoint)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        # configure manually authentication backend
        server.auth_backend.user_map[client_id] = password

        yield server.start()
        yield client.start()
        future = yield client.string.lower('FOO')
        future2 = yield client.string.lower('FOO_JJ')
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        assert future.result(timeout=self.timeout) == 'foo'
        assert future2.result(timeout=self.timeout) == 'foo_jj'
        yield server.stop()
        yield client.stop()

    @tornado.testing.gen_test()
    def test_untrusted_curve_with_wrong_password(self):
        from pyzmq_rpc import Client, Server
        from pyzmq_rpc.interfaces import UnauthorizedError

        client_id = 'john'
        server_id = 'server'
        endpoint = 'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'untrusted_curve'
        password = 's3cret!'

        client = Client(client_id, server_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        private_key=client_secret,
                        peer_public_key=server_public,
                        password=password,
                        io_loop=self.io_loop)

        server = Server(server_id,
                        security_plugin=security_plugin,
                        public_key=server_public,
                        private_key=server_secret,
                        io_loop=self.io_loop)

        server.bind(endpoint)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        # configure manually authentication backend
        server.auth_backend.user_map[client_id] = password + 'Looser'

        yield server.start()
        yield client.start()
        future = yield client.string.lower('IMSCREAMING')
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        with pytest.raises(UnauthorizedError):
            future.result(timeout=self.timeout)
        yield server.stop()
        yield client.stop()
