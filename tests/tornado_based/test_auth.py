from __future__ import unicode_literals

from future.builtins import str
from concurrent.futures import TimeoutError
import pytest
import tornado.testing
import zmq
from zmq.eventloop import ioloop
from zmq.utils import z85
from zope.interface.verify import verifyClass


ioloop.install()


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

        server_id = b'server'
        endpoint = b'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()
        security_plugin = 'trusted_curve'

        server = Server(server_id, security_plugin=security_plugin,
                        public_key=server_public,
                        secret_key=server_secret,
                        io_loop=self.io_loop)
        server.bind(endpoint)

        bob_public, bob_secret = server.auth_backend.known_identities[b'bob']
        client = Client(server_id,
                        user_id=b'bob',
                        security_plugin=security_plugin,
                        public_key=bob_public,
                        secret_key=bob_secret,
                        peer_public_key=server_public,
                        io_loop=self.io_loop)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        yield server.start()
        yield client.start()

        register_rpc(name='string.lower')(str.lower)

        result = yield client.string.lower('FOO')
        assert result == 'foo'
        server.stop()
        client.stop()

    @tornado.testing.gen_test
    def test_trusted_curve_with_wrong_peer_public_key(self):
        from pseud import Client, Server
        from pseud.utils import register_rpc
        server_id = b'server'
        endpoint = 'inproc://{}'.format(__name__).encode()
        endpoint = b'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()

        server = Server(server_id, security_plugin='trusted_curve',
                        public_key=server_public,
                        secret_key=server_secret,
                        io_loop=self.io_loop)
        server.bind(endpoint)

        alice_public, alice_secret = \
            server.auth_backend.known_identities[b'alice']
        client = Client(server_id,
                        user_id=b'alice',
                        security_plugin='trusted_curve',
                        public_key=alice_public,
                        secret_key=alice_secret,
                        peer_public_key=z85.encode(b'R' * 32),
                        timeout=.5,
                        io_loop=self.io_loop)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        yield server.start()
        yield client.start()

        register_rpc(name='string.lower')(str.lower)

        with pytest.raises(TimeoutError):
            yield client.string.lower('BAR')
        server.stop()
        client.stop()

    @tornado.testing.gen_test()
    def test_untrusted_curve_with_allowed_password(self):
        from pseud import Client, Server
        from pseud.utils import register_rpc
        from pseud._tornado import async_sleep

        client_id = b'john'
        server_id = b'server'
        endpoint = b'tcp://127.0.0.1:8999'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'untrusted_curve'
        password = b's3cret!'

        client = Client(server_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        secret_key=client_secret,
                        peer_public_key=server_public,
                        user_id=client_id,
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

        register_rpc(name='string.lower')(str.lower)

        future = client.string.lower('FOO')
        future2 = client.string.lower('FOO_JJ')
        yield async_sleep(self.io_loop, .01)
        future3 = server.send_to(client_id).string.lower('ABC')
        result = yield future
        result2 = yield future2
        result3 = yield future3
        assert result == 'foo'
        assert result2 == 'foo_jj'
        assert result3 == 'abc'
        server.stop()
        client.stop()

    @tornado.testing.gen_test
    def test_untrusted_curve_with_allowed_password_and_client_disconnect(self):
        from pseud import Client, Server
        from pseud._tornado import async_sleep

        client_id = b'john'
        server_id = b'server'
        endpoint = b'tcp://127.0.0.1:8999'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'untrusted_curve'
        password = b's3cret!'

        client = Client(server_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        secret_key=client_secret,
                        peer_public_key=server_public,
                        user_id=client_id,
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

        server.register_rpc(name='string.lower')(str.lower)

        result = yield client.string.lower('FOO')
        assert result == 'foo'
        # Simulate disconnection and reconnection with new identity
        client.disconnect(endpoint)
        client.connect(endpoint)
        yield async_sleep(self.io_loop, .15)
        result = yield client.string.lower('ABC')
        assert result == 'abc'
        server.stop()
        client.stop()

    @tornado.testing.gen_test()
    def test_untrusted_curve_with_wrong_password(self):
        from pseud import Client, Server
        from pseud.interfaces import UnauthorizedError
        from pseud.utils import register_rpc

        client_id = b'john'
        server_id = b'server'
        endpoint = b'tcp://127.0.0.1:8998'
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()
        security_plugin = 'untrusted_curve'
        password = b's3cret!'

        client = Client(server_id,
                        user_id=client_id,
                        security_plugin=security_plugin,
                        public_key=client_public,
                        secret_key=client_secret,
                        peer_public_key=server_public,
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
        server.auth_backend.user_map[client_id] = password + b'Looser'

        yield server.start()
        yield client.start()

        register_rpc(name='string.lower')(str.lower)

        future = client.string.lower(b'IMSCREAMING')
        with pytest.raises(UnauthorizedError):
            yield future
        server.stop()
        client.stop()

    @pytest.mark.skipif(zmq.zmq_version_info() < (4, 1, 0),
                        reason='Needs pyzmq build with libzmq >= 4.1.0')
    @tornado.testing.gen_test()
    def test_client_can_reconnect(self):
        from pseud import Client, Server
        from pseud._tornado import async_sleep

        server_id = b'server'
        endpoint = b'tcp://127.0.0.1:8989'
        server_public, server_secret = zmq.curve_keypair()
        security_plugin = 'trusted_curve'

        server = Server(server_id, security_plugin=security_plugin,
                        public_key=server_public,
                        secret_key=server_secret,
                        io_loop=self.io_loop)
        server.bind(endpoint)

        bob_public, bob_secret = server.auth_backend.known_identities[b'bob']
        client = Client(server_id,
                        user_id=b'bob',
                        security_plugin=security_plugin,
                        public_key=bob_public,
                        secret_key=bob_secret,
                        peer_public_key=server_public,
                        io_loop=self.io_loop)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        yield server.start()
        yield client.start()

        server.register_rpc(name='string.upper')(str.upper)

        result = yield client.string.upper('hello')
        assert result == 'HELLO'

        client.disconnect(endpoint)
        client.connect(endpoint)
        yield async_sleep(self.io_loop, .1)

        result = yield client.string.upper('hello2')
        assert result == 'HELLO2'

        client.stop()
        server.stop()

    @tornado.testing.gen_test()
    def test_server_can_send_to_trustable_peer_identity(self):
        """
        Uses internal metadata of zmq.Frame.get() to fetch identity of sender
        """
        from pseud import Client, Server

        server_id = b'server'
        endpoint = b'tcp://127.0.0.1:8989'
        server_public, server_secret = zmq.curve_keypair()
        security_plugin = 'trusted_curve'

        server = Server(server_id, security_plugin=security_plugin,
                        public_key=server_public,
                        secret_key=server_secret,
                        io_loop=self.io_loop)
        server.bind(endpoint)

        bob_public, bob_secret = server.auth_backend.known_identities[b'bob']
        client = Client(server_id,
                        user_id=b'bob',
                        security_plugin=security_plugin,
                        public_key=bob_public,
                        secret_key=bob_secret,
                        peer_public_key=server_public,
                        io_loop=self.io_loop)
        client.connect(endpoint)
        assert server.socket.mechanism == zmq.CURVE
        assert client.socket.mechanism == zmq.CURVE

        yield server.start()
        yield client.start()

        @server.register_rpc(with_identity=True)
        def echo(peer_identity, message):
            return peer_identity, message

        result = yield client.echo(b'one')
        if zmq.zmq_version_info() >= (4, 1, 0):
            assert result == [b'bob', b'one']
        else:
            assert result == [b'', b'one']
        server.stop()
        client.stop()
