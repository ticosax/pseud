import time

from concurrent.futures import TimeoutError
import pytest
import tornado.testing
import zmq
from zmq.utils import z85
from zope.interface.verify import verifyClass


def test_noop_auth_backend_client():
    from pseud.auth import NoOpAuthenticationBackendForClient
    from pseud.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend,
                       NoOpAuthenticationBackendForClient)


def test_noop_auth_backend_server():
    from pseud.auth import NoOpAuthenticationBackendForServer
    from pseud.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend,
                       NoOpAuthenticationBackendForServer)


def test_trusted_curve_client():
    from pseud.auth import CurveWithTrustedKeyForClient
    from pseud.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend, CurveWithTrustedKeyForClient)


def test_trusted_curve_server():
    from pseud.auth import CurveWithTrustedKeyForServer
    from pseud.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend, CurveWithTrustedKeyForServer)


def test_untrusted_curve_client():
    from pseud.auth import CurveWithUntrustedKeyForClient
    from pseud.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend, CurveWithUntrustedKeyForClient)


def test_untrusted_curve_server():
    from pseud.auth import CurveWithUntrustedKeyForServer
    from pseud.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend, CurveWithUntrustedKeyForServer)


class CurveTestCase(tornado.testing.AsyncTestCase):
    timeout = 2

    @tornado.testing.gen_test
    def test_trusted_curve(self):
        from pseud import Client, Server
        from pseud.utils import register_rpc

        client_id = 'client'
        server_id = 'server'
        endpoint = 'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'trusted_curve'
        client = Client(server_id,
                        identity=client_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        secret_key=client_secret,
                        peer_public_key=server_public,
                        io_loop=self.io_loop)

        server = Server(server_id, security_plugin=security_plugin,
                        public_key=server_public,
                        secret_key=server_secret,
                        io_loop=self.io_loop)

        server.bind(endpoint)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        yield server.start()
        yield client.start()

        import string
        register_rpc(name='string.lower')(string.lower)

        future = client.string.lower('FOO')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result(timeout=self.timeout) == 'foo'
        server.stop()
        client.stop()

    @tornado.testing.gen_test
    def test_trusted_curve_with_wrong_peer_public_key(self):
        from pseud import Client, Server
        from pseud.utils import register_rpc
        client_id = 'client'
        server_id = 'server'
        endpoint = 'inproc://{}'.format(__name__)
        endpoint = 'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        client = Client(server_id,
                        identity=client_id,
                        security_plugin='trusted_curve',
                        public_key=client_public,
                        secret_key=client_secret,
                        peer_public_key=z85.encode('R' * 32),
                        io_loop=self.io_loop)

        server = Server(server_id, security_plugin='trusted_curve',
                        public_key=server_public,
                        secret_key=server_secret,
                        io_loop=self.io_loop)

        server.bind(endpoint)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        server.start()
        client.start()

        import string
        register_rpc(name='string.lower')(string.lower)

        future = client.string.lower('BAR')
        self.io_loop.add_timeout(self.io_loop.time() + .5,
                                 self.stop)
        self.wait()
        with pytest.raises(TimeoutError):
            future.result(timeout=self.timeout)
        server.stop()
        client.stop()

    @tornado.testing.gen_test()
    def test_untrusted_curve_with_allowed_password(self):
        from pseud import Client, Server
        from pseud.utils import register_rpc
        from pseud._tornado import async_sleep

        client_id = 'john'
        server_id = 'server'
        endpoint = 'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'untrusted_curve'
        password = 's3cret!'

        client = Client(server_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        secret_key=client_secret,
                        peer_public_key=server_public,
                        login=client_id,
                        password=password,
                        io_loop=self.io_loop)

        server = Server(server_id,
                        security_plugin=security_plugin,
                        public_key=server_public,
                        secret_key=server_secret,
                        io_loop=self.io_loop)

        server.bind(endpoint)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        # configure manually authentication backend
        server.auth_backend.user_map[client_id] = password

        yield server.start()
        yield client.start()

        import string
        register_rpc(name='string.lower')(string.lower)

        future = client.string.lower('FOO')
        future2 = client.string.lower('FOO_JJ')
        yield async_sleep(self.io_loop, .01)
        future3 = server.send_to(client_id).string.lower('ABC')
        self.io_loop.add_future(future3, self.stop)
        self.wait()
        assert future.result() == 'foo'
        assert future2.result() == 'foo_jj'
        assert future3.result() == 'abc'
        server.stop()
        client.stop()

    @tornado.testing.gen_test
    def test_untrusted_curve_with_allowed_password_and_client_disconnect(self):
        from pseud import Client, Server
        from pseud.utils import register_rpc

        client_id = 'john'
        server_id = 'server'
        endpoint = 'tcp://127.0.0.1:8999'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'untrusted_curve'
        password = 's3cret!'

        client = Client(server_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        secret_key=client_secret,
                        peer_public_key=server_public,
                        login=client_id,
                        password=password,
                        timeout=1,
                        io_loop=self.io_loop)

        server = Server(server_id,
                        security_plugin=security_plugin,
                        public_key=server_public,
                        secret_key=server_secret,
                        io_loop=self.io_loop)

        server.bind(endpoint)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        # configure manually authentication backend
        server.auth_backend.user_map[client_id] = password

        yield server.start()
        yield client.start()

        import string
        register_rpc(name='string.lower')(string.lower)

        future = client.string.lower('FOO')
        self.io_loop.add_timeout(self.io_loop.time() + .2, self.io_loop.stop)
        self.io_loop.start()
        assert future.result() == 'foo'
        # Simulate disconnection and reconnection with new identity
        client.disconnect(endpoint)
        client.identity = 'wow-doge'
        client.connect(endpoint)
        self.io_loop.run_sync(lambda *args, **kw: time.sleep(.1))
        future = client.string.lower('ABC')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result() == 'abc'
        server.stop()
        client.stop()

    @tornado.testing.gen_test()
    def test_untrusted_curve_with_wrong_password(self):
        from pseud import Client, Server
        from pseud.interfaces import UnauthorizedError
        from pseud.utils import register_rpc

        client_id = 'john'
        server_id = 'server'
        endpoint = 'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'untrusted_curve'
        password = 's3cret!'

        client = Client(server_id,
                        identity=client_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        secret_key=client_secret,
                        peer_public_key=server_public,
                        login=client_id,
                        password=password,
                        io_loop=self.io_loop)

        server = Server(server_id,
                        security_plugin=security_plugin,
                        public_key=server_public,
                        secret_key=server_secret,
                        io_loop=self.io_loop)

        server.bind(endpoint)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        # configure manually authentication backend
        server.auth_backend.user_map[client_id] = password + 'Looser'

        yield server.start()
        yield client.start()

        import string
        register_rpc(name='string.lower')(string.lower)

        future = client.string.lower('IMSCREAMING')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        with pytest.raises(UnauthorizedError):
            future.result(timeout=self.timeout)
        server.stop()
        client.stop()

    @pytest.mark.skipif(zmq.zmq_version_info() < (4, 1, 0),
                        reason='Needs zeromq build with libzmq >= 4.1.0')
    def test_client_can_reconnect(self):
        from pseud import Client, Server

        client_id = 'client'
        server_id = 'server'
        endpoint = 'tcp://127.0.0.1:8989'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'trusted_curve'

        client = Client(server_id,
                        identity=client_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        secret_key=client_secret,
                        peer_public_key=server_public,
                        io_loop=self.io_loop)

        server = Server(server_id, security_plugin=security_plugin,
                        public_key=server_public,
                        secret_key=server_secret,
                        io_loop=self.io_loop)

        server.bind(endpoint)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        started = server.start()

        self.io_loop.add_future(started, self.stop)
        self.wait()

        import string
        server.register_rpc(name='string.upper')(string.upper)

        future = client.string.upper('hello')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result() == 'HELLO'

        client.disconnect(endpoint)
        client.connect(endpoint)
        future = client.string.upper('hello')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result() == 'HELLO'

        client.stop()
        server2.stop()
