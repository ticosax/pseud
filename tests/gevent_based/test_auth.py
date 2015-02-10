import pytest
from zope.interface.verify import verifyClass
gevent = pytest.importorskip('gevent')
from gevent.timeout import Timeout  # NOQA
import zmq.green as zmq  # NOQA
from zmq.utils import z85  # NOQA


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


def test_trusted_curve():
    from pseud._gevent import Client, Server
    from pseud.utils import register_rpc

    server_id = 'server'
    endpoint = 'tcp://127.0.0.1:8998'
    server_public, server_secret = zmq.curve_keypair()
    security_plugin = 'trusted_curve'

    server = Server(server_id, security_plugin=security_plugin,
                    public_key=server_public,
                    secret_key=server_secret)
    server.bind(endpoint)
    bob_public, bob_secret = server.auth_backend.known_identities[b'bob']
    client = Client(server_id,
                    security_plugin=security_plugin,
                    public_key=bob_public,
                    secret_key=bob_secret,
                    peer_public_key=server_public)

    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    server.start()
    client.start()
    import string
    register_rpc(name='string.lower')(string.lower)
    future = client.string.lower('FOO')
    assert future.get() == 'foo'
    server.stop()
    client.stop()


def test_trusted_curve_with_wrong_peer_public_key():
    from pseud._gevent import Client, Server
    server_id = 'server'
    endpoint = 'inproc://{}'.format(__name__)
    endpoint = 'tcp://127.0.0.1:8998'
    server_public, server_secret = zmq.curve_keypair()
    client_public, client_secret = zmq.curve_keypair()
    client = Client(server_id,
                    security_plugin='trusted_curve',
                    public_key=client_public,
                    secret_key=client_secret,
                    peer_public_key=z85.encode('R' * 32))

    server = Server(server_id, security_plugin='trusted_curve',
                    public_key=server_public,
                    secret_key=server_secret)

    server.bind(endpoint)
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    server.start()
    future = client.string.lower('BAR')
    with pytest.raises(Timeout):
        future.get(timeout=0.1)
    server.stop()
    client.stop()


def test_untrusted_curve_with_allowed_password():
    from pseud._gevent import Client, Server
    from pseud.utils import register_rpc

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
                    user_id=client_id,
                    password=password)

    server = Server(server_id,
                    security_plugin=security_plugin,
                    public_key=server_public,
                    secret_key=server_secret)

    server.bind(endpoint)
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    # configure manually authentication backend
    server.auth_backend.user_map[client_id] = password

    server.start()
    import string
    register_rpc(name='string.lower')(string.lower)
    future = client.string.lower('FOO')
    future2 = client.string.lower('FOO_JJ')
    assert future.get() == 'foo'
    assert future2.get() == 'foo_jj'
    future3 = server.send_to(client_id).string.lower('ABC')
    assert future3.get() == 'abc'
    server.stop()
    client.stop()


def test_untrusted_curve_with_allowed_password_and_client_disconnect():
    from pseud._gevent import Client, Server
    from pseud.utils import register_rpc

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
                    user_id=client_id,
                    password=password)

    server = Server(server_id,
                    security_plugin=security_plugin,
                    public_key=server_public,
                    secret_key=server_secret)

    server.bind(endpoint)
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    # configure manually authentication backend
    server.auth_backend.user_map[client_id] = password

    server.start()
    import string
    register_rpc(name='string.lower')(string.lower)
    future = client.string.lower('FOO')
    assert future.get() == 'foo'
    # Simulate disconnection and reconnection with new identity
    client.socket.disconnect(endpoint)
    client.socket.identity = 'wow-doge'
    client.socket.connect(endpoint)
    gevent.sleep(.1)  # Warmup
    assert client.string.lower('ABC').get() == 'abc'
    server.stop()
    client.stop()


def test_untrusted_curve_with_wrong_password():
    from pseud._gevent import Client, Server
    from pseud.interfaces import UnauthorizedError
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
                    user_id=client_id,
                    password=password)

    server = Server(server_id,
                    security_plugin=security_plugin,
                    public_key=server_public,
                    secret_key=server_secret)

    server.bind(endpoint)
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    # configure manually authentication backend
    server.auth_backend.user_map[client_id] = password + 'Looser'

    server.start()
    client.start()
    import string
    register_rpc(name='string.lower')(string.lower)
    future = client.string.lower('IMSCREAMING')
    with pytest.raises(UnauthorizedError):
        future.get()
    server.stop()
    client.stop()


def test_client_can_reconnect():
    from pseud._gevent import Client, Server

    server_id = 'server'
    endpoint = 'tcp://127.0.0.1:8989'
    server_public, server_secret = zmq.curve_keypair()
    client_public, client_secret = zmq.curve_keypair()
    security_plugin = 'trusted_curve'

    server = Server(server_id, security_plugin=security_plugin,
                    public_key=server_public,
                    secret_key=server_secret)
    server.bind(endpoint)
    bob_public, bob_secret = server.auth_backend.known_identities[b'bob']
    client = Client(server_id,
                    security_plugin=security_plugin,
                    public_key=bob_public,
                    secret_key=bob_secret,
                    peer_public_key=server_public)

    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    server.start()

    import string
    server.register_rpc(name='string.upper')(string.upper)

    future = client.string.upper('hello')
    assert future.get() == 'HELLO'

    client.disconnect(endpoint)
    client.connect(endpoint)
    gevent.sleep(.1)
    future = client.string.upper('hello')
    assert future.get() == 'HELLO'

    client.stop()
    server.stop()


def test_server_can_send_to_trustable_peer_identity():
    """
    Uses internal metadata of zmq.Frame.get() to fetch identity of sender
    """
    from pseud._gevent import Client, Server

    server_id = 'server'
    endpoint = 'tcp://127.0.0.1:8989'
    server_public, server_secret = zmq.curve_keypair()
    security_plugin = 'trusted_curve'

    server = Server(server_id, security_plugin=security_plugin,
                    public_key=server_public,
                    secret_key=server_secret,
                    )
    server.bind(endpoint)

    bob_public, bob_secret = server.auth_backend.known_identities['bob']
    client = Client(server_id,
                    user_id='bob',
                    security_plugin=security_plugin,
                    public_key=bob_public,
                    secret_key=bob_secret,
                    peer_public_key=server_public,
                    )
    client.connect(endpoint)
    assert server.socket.mechanism == zmq.CURVE
    assert client.socket.mechanism == zmq.CURVE

    server.start()
    client.start()

    @server.register_rpc(with_identity=True)
    def echo(peer_identity, message):
        return peer_identity, message

    result = client.echo('one').get()
    if zmq.zmq_version_info() >= (4, 1, 0):
        assert result == ('bob', 'one')
    else:
        assert result == ('', 'one')
    server.stop()
    client.stop()
