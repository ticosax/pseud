import pytest
import zmq.green as zmq  # NOQA


def make_one_server(identity, proxy_to=None):
    from pseud._gevent import Server
    from pseud import auth, heartbeat, predicate  # NOQA
    server = Server(identity, proxy_to=proxy_to)
    return server


def make_one_client(identity, peer_identity):
    from pseud._gevent import Client
    from pseud import auth, heartbeat, predicate  # NOQA
    client = Client(identity, peer_identity)
    return client


def test_client_can_send():
    from pseud.utils import register_rpc
    client_id = 'client'
    server_id = 'server'
    endpoint = 'inproc://here'

    server = make_one_server(server_id)

    client = make_one_client(client_id, server_id)

    server.bind(endpoint)
    server.start()

    client.connect(endpoint)
    client.start()

    import string
    register_rpc(name='string.upper')(string.upper)

    future = client.string.upper('hello')
    assert future.get() == 'HELLO'
    client.stop()
    server.stop()


def test_server_can_send():
    from pseud.utils import peer_identity_provider
    from pseud.utils import register_rpc

    client_id = 'client'
    server_id = 'server'
    endpoint = 'inproc://here'

    server = make_one_server(server_id)

    client = make_one_client(client_id, server_id)

    server.bind(endpoint)
    server.start()

    client.connect(endpoint)
    client.start()

    import string
    register_rpc(name='string.lower')(string.lower)

    with peer_identity_provider(server, client_id):
        future = server.string.lower('SCREAM')

    assert future.get() == 'scream'
    client.stop()
    server.stop()


def test_server_can_send_to_several_client():
    from pseud.utils import peer_identity_provider
    from pseud.utils import register_rpc
    server_id = 'server'
    endpoint = 'inproc://here'

    server = make_one_server(server_id, endpoint)

    client1 = make_one_client('client1', server_id)
    client2 = make_one_client('client2', server_id)

    server.bind(endpoint)
    client1.connect(endpoint)
    client2.connect(endpoint)
    server.start()
    client1.start()
    client2.start()

    import string
    register_rpc(name='string.lower')(string.lower)

    with peer_identity_provider(server, 'client1'):
        future1 = server.string.lower('SCREAM1')

    with peer_identity_provider(server, 'client2'):
        future2 = server.string.lower('SCREAM2')

    assert future1.get() == 'scream1'
    assert future2.get() == 'scream2'
    client1.stop()
    client2.stop()
    server.stop()


def test_raises_if_module_not_found():
    from pseud import auth, heartbeat  # NOQA
    from pseud.interfaces import ServiceNotFoundError
    server_id = 'server'
    endpoint = 'inproc://here'
    server = make_one_server(server_id)

    client = make_one_client('client', server_id)
    server.bind(endpoint)
    client.connect(endpoint)
    server.start()
    client.start()
    future = client.string.doesnotexists('QWERTY')
    with pytest.raises(ServiceNotFoundError):
            future.get()
    server.stop()
    client.close()


def test_server_can_proxy_another_server():
    """
    Client1 --> Server1.string.lower()
    Client2 --> Server2(Server1.string.lower())
    """
    from pseud.interfaces import ServiceNotFoundError
    from pseud.utils import get_rpc_callable, register_rpc

    server1 = make_one_server('server1')
    server2 = make_one_server('server2',
                              proxy_to=server1)

    client1 = make_one_client('client1', 'server1')
    client2 = make_one_client('client2', 'server2')

    server1.bind('inproc://server1')
    server2.bind('inproc://server2')
    client1.connect('inproc://server1')
    client2.connect('inproc://server2')
    server1.start()
    server2.start()

    import string
    # Local registration
    server1.register_rpc(name='str.lower')(string.lower)

    # Global registration
    register_rpc(name='str.upper')(string.upper)

    # local registration only to proxy
    server2.register_rpc(name='bla.lower')(string.lower)

    with pytest.raises(ServiceNotFoundError):
        get_rpc_callable('str.lower', registry=server2.registry)

    with pytest.raises(ServiceNotFoundError):
        get_rpc_callable('bla.lower', registry=server1.registry)

    with pytest.raises(ServiceNotFoundError):
        get_rpc_callable('bla.lower')

    with pytest.raises(ServiceNotFoundError):
        assert get_rpc_callable('str.lower')

    assert get_rpc_callable('str.lower',
                            registry=server1.registry)('L') == 'l'

    assert client1.str.lower('SCREAM').get() == 'scream'
    assert client2.str.lower('SCREAM').get() == 'scream'
    assert client2.bla.lower('SCREAM').get() == 'scream'
    assert client1.str.upper('whisper').get() == 'WHISPER'
    assert client2.str.upper('whisper').get() == 'WHISPER'

    client1.stop()
    client2.stop()
    server1.stop()
    server2.stop()
