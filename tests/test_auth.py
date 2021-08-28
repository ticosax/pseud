import asyncio

import pytest
import zmq
from zmq.utils import z85
from zope.interface.verify import verifyClass


def test_noop_auth_backend_client():
    from pseud.auth import NoOpAuthenticationBackendForClient
    from pseud.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend, NoOpAuthenticationBackendForClient)


def test_noop_auth_backend_server():
    from pseud.auth import NoOpAuthenticationBackendForServer
    from pseud.interfaces import IAuthenticationBackend

    assert verifyClass(IAuthenticationBackend, NoOpAuthenticationBackendForServer)


@pytest.mark.asyncio
async def test_trusted_curve(loop, unused_tcp_port, trusted_curve_auth_backend):
    from pseud import Client, Server
    from pseud.utils import register_rpc

    server_id = b'server'
    endpoint = f'tcp://127.0.0.1:{unused_tcp_port}'
    server_public, server_secret = zmq.curve_keypair()
    security_plugin = 'trusted_curve'

    server = Server(
        server_id,
        security_plugin=security_plugin,
        public_key=server_public,
        secret_key=server_secret,
        loop=loop,
    )
    server.bind(endpoint)

    bob_public, bob_secret = server.auth_backend.known_identities[b'bob']
    client = Client(
        server_id,
        user_id=b'bob',
        security_plugin=security_plugin,
        public_key=bob_public,
        secret_key=bob_secret,
        peer_public_key=server_public,
        loop=loop,
    )
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    register_rpc(name='string.lower')(str.lower)

    async with server, client:
        result = await client.string.lower('FOO')
        assert result == 'foo'


@pytest.mark.asyncio
async def test_trusted_curve_with_wrong_peer_public_key(loop, unused_tcp_port_factory):
    from pseud import Client, Server
    from pseud.utils import register_rpc

    server_id = b'server'
    port = unused_tcp_port_factory()
    endpoint = f'tcp://127.0.0.1:{port}'
    server_public, server_secret = zmq.curve_keypair()

    server = Server(
        server_id,
        security_plugin='trusted_curve',
        public_key=server_public,
        secret_key=server_secret,
        loop=loop,
    )
    server.bind(endpoint)

    alice_public, alice_secret = server.auth_backend.known_identities[b'alice']
    client = Client(
        server_id,
        user_id=b'alice',
        security_plugin='trusted_curve',
        public_key=alice_public,
        secret_key=alice_secret,
        peer_public_key=z85.encode(b'R' * 32),
        timeout=0.5,
        loop=loop,
    )
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    register_rpc(name='string.lower')(str.lower)

    async with server, client:
        with pytest.raises(asyncio.TimeoutError):
            await client.string.lower('BAR')


@pytest.mark.asyncio
async def test_untrusted_curve_with_allowed_password(
    loop, unused_tcp_port, untrusted_curve_auth_backend
):
    from pseud import Client, Server
    from pseud.utils import register_rpc

    client_id = b'john'
    server_id = b'server'
    endpoint = f'tcp://127.0.0.1:{unused_tcp_port}'
    server_public, server_secret = zmq.curve_keypair()
    client_public, client_secret = zmq.curve_keypair()
    security_plugin = 'untrusted_curve'
    password = b's3cret!'

    client = Client(
        server_id,
        security_plugin=security_plugin,
        public_key=client_public,
        secret_key=client_secret,
        peer_public_key=server_public,
        user_id=client_id,
        password=password,
        loop=loop,
    )

    server = Server(
        server_id,
        security_plugin=security_plugin,
        public_key=server_public,
        secret_key=server_secret,
        loop=loop,
    )

    server.bind(endpoint)
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    # configure manually authentication backend
    server.auth_backend.user_map[client_id] = password

    register_rpc(name='string.lower')(str.lower)

    async with server, client:
        result = await client.string.lower('FOO')
        result2 = await client.string.lower('FOO_JJ')
        result3 = await server.send_to(client_id).string.lower('ABC')
        assert result == 'foo'
        assert result2 == 'foo_jj'
        assert result3 == 'abc'


@pytest.mark.asyncio
async def test_untrusted_curve_with_allowed_password_and_client_disconnect(
    loop, unused_tcp_port
):
    from pseud import Client, Server

    client_id = b'john'
    server_id = b'server'
    endpoint = f'tcp://127.0.0.1:{unused_tcp_port}'
    server_public, server_secret = zmq.curve_keypair()
    client_public, client_secret = zmq.curve_keypair()
    security_plugin = 'untrusted_curve'
    password = b's3cret!'

    client = Client(
        server_id,
        security_plugin=security_plugin,
        public_key=client_public,
        secret_key=client_secret,
        peer_public_key=server_public,
        user_id=client_id,
        password=password,
        timeout=1,
        loop=loop,
    )

    server = Server(
        server_id,
        security_plugin=security_plugin,
        public_key=server_public,
        secret_key=server_secret,
        loop=loop,
    )

    server.bind(endpoint)
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    # configure manually authentication backend
    server.auth_backend.user_map[client_id] = password

    server.register_rpc(name='string.lower')(str.lower)

    async with server, client:
        result = await client.string.lower('FOO')
        assert result == 'foo'
        # Simulate disconnection and reconnection with new identity
        client.disconnect(endpoint)
        client.connect(endpoint)
        await asyncio.sleep(0.1)
        result = await client.string.lower('ABC')
        assert result == 'abc'


@pytest.mark.asyncio
async def test_untrusted_curve_with_wrong_password(loop, unused_tcp_port):
    from pseud import Client, Server
    from pseud.interfaces import UnauthorizedError
    from pseud.utils import register_rpc

    client_id = b'john'
    server_id = b'server'
    endpoint = f'tcp://127.0.0.1:{unused_tcp_port}'
    server_public, server_secret = zmq.curve_keypair()
    client_public, client_secret = zmq.curve_keypair()
    security_plugin = 'untrusted_curve'
    password = b's3cret!'

    client = Client(
        server_id,
        user_id=client_id,
        security_plugin=security_plugin,
        public_key=client_public,
        secret_key=client_secret,
        peer_public_key=server_public,
        password=password,
        loop=loop,
    )

    server = Server(
        server_id,
        security_plugin=security_plugin,
        public_key=server_public,
        secret_key=server_secret,
        loop=loop,
    )

    server.bind(endpoint)
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    # configure manually authentication backend
    server.auth_backend.user_map[client_id] = password + b'Looser'

    register_rpc(name='string.lower')(str.lower)

    async with server, client:
        with pytest.raises(UnauthorizedError):
            await client.string.lower(b'IMSCREAMING')


@pytest.mark.asyncio
async def test_client_can_reconnect(loop, unused_tcp_port_factory):
    from pseud import Client, Server

    port = unused_tcp_port_factory()
    server_id = b'server'
    endpoint = f'tcp://127.0.0.1:{port}'
    server_public, server_secret = zmq.curve_keypair()
    security_plugin = 'trusted_curve'

    server = Server(
        server_id,
        security_plugin=security_plugin,
        public_key=server_public,
        secret_key=server_secret,
        loop=loop,
    )
    server.bind(endpoint)

    bob_public, bob_secret = server.auth_backend.known_identities[b'bob']
    client = Client(
        server_id,
        user_id=b'bob',
        security_plugin=security_plugin,
        public_key=bob_public,
        secret_key=bob_secret,
        peer_public_key=server_public,
        loop=loop,
    )
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    server.register_rpc(name='string.upper')(str.upper)

    async with server, client:
        result = await client.string.upper('hello')
        assert result == 'HELLO'

        client.disconnect(endpoint)
        client.connect(endpoint)
        await asyncio.sleep(0.01)

        result = await client.string.upper('hello2')
        assert result == 'HELLO2'


@pytest.mark.asyncio
async def test_server_can_send_to_trustable_peer_identity(loop, unused_tcp_port):
    """
    Uses internal metadata of zmq.Frame.get() to fetch identity of sender
    """
    from pseud import Client, Server

    server_id = b'server'
    endpoint = f'tcp://127.0.0.1:{unused_tcp_port}'
    server_public, server_secret = zmq.curve_keypair()
    security_plugin = 'trusted_curve'

    server = Server(
        server_id,
        security_plugin=security_plugin,
        public_key=server_public,
        secret_key=server_secret,
        loop=loop,
    )
    server.bind(endpoint)

    bob_public, bob_secret = server.auth_backend.known_identities[b'bob']
    client = Client(
        server_id,
        user_id=b'bob',
        security_plugin=security_plugin,
        public_key=bob_public,
        secret_key=bob_secret,
        peer_public_key=server_public,
        loop=loop,
    )
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    @server.register_rpc(with_identity=True)
    def echo(peer_identity, message):
        return peer_identity, message

    async with server, client:
        result = await client.echo(b'one')
        if zmq.zmq_version_info() >= (4, 1, 0):
            assert result == (b'bob', b'one')
        else:
            assert result == (b'', b'one')
