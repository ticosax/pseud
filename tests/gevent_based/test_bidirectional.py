import pytest
import zmq.green as zmq  # NOQA


def make_one_server(identity, endpoint):
    from pybidirpc._gevent import Server
    from pybidirpc import auth, heartbeat, predicate  # NOQA
    server = Server(identity)
    return server


def make_one_client(identity, peer_identity):
    from pybidirpc._gevent import Client
    from pybidirpc import auth, heartbeat, predicate  # NOQA
    client = Client(identity, peer_identity)
    return client


def test_client_can_send():
    from pybidirpc.utils import register_rpc
    client_id = 'client'
    server_id = 'server'
    endpoint = 'inproc://here'

    server = make_one_server(server_id, endpoint)

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
    from pybidirpc.utils import peer_identity_provider
    from pybidirpc.utils import register_rpc

    client_id = 'client'
    server_id = 'server'
    endpoint = 'inproc://here'

    server = make_one_server(server_id, endpoint)

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
    from pybidirpc.utils import peer_identity_provider
    from pybidirpc.utils import register_rpc
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
    from pybidirpc import auth, heartbeat  # NOQA
    from pybidirpc.interfaces import ServiceNotFoundError
    server_id = 'server'
    endpoint = 'inproc://here'
    server = make_one_server(server_id, endpoint)

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
