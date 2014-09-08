import pytest
gevent = pytest.importorskip('gevent')
from gevent.timeout import Timeout
import zmq.green as zmq


def make_one_server(identity, proxy_to=None,
                    security_plugin='noop_auth_backend'):
    from pseud._gevent import Server
    server = Server(identity,
                    proxy_to=proxy_to,
                    security_plugin=security_plugin)
    return server


def make_one_client(peer_routing_id, security_plugin='noop_auth_backend',
                    user_id=None, password=None):
    from pseud._gevent import Client
    client = Client(peer_routing_id,
                    security_plugin=security_plugin,
                    user_id=user_id,
                    password=password,
                    )
    return client


def test_client_can_send():
    server_id = b'server'
    endpoint = b'inproc://here'

    server = make_one_server(server_id)

    client = make_one_client(server_id)

    server.bind(endpoint)
    server.start()

    client.connect(endpoint)
    client.start()

    register_rpc(name='string.upper')(str.upper)

    future = client.string.upper('hello')
    assert future.get() == 'HELLO'
    client.stop()
    server.stop()


@pytest.mark.skipif((zmq.zmq_version_info() < (4, 1, 0) or
                     zmq.pyzmq_version_info() < (14, 4)),
                    reason='Needs pyzmq build with libzmq >= 4.1.0')
def test_server_can_send():
    from pseud.utils import register_rpc

    client_id = b'client'
    server_id = b'server'
    endpoint = b'tcp://127.0.0.1:5000'

    # PLAIN
    server = make_one_server(server_id, security_plugin='plain')

    client = make_one_client(server_id, user_id=client_id,
                             password=client_id,
                             security_plugin='plain')

    server.bind(endpoint)
    server.start()

    client.connect(endpoint)
    client.start()

    register_rpc(name='string.lower')(str.lower)

    result = client.string.lower('TATA').get()
    assert result == 'tata'

    future = server.send_to(client_id).string.lower('SCREAM')

    assert future.get() == 'scream'
    client.stop()
    server.stop()


@pytest.mark.skipif((zmq.zmq_version_info() < (4, 1, 0) or
                     zmq.pyzmq_version_info() < (14, 4)),
                    reason='Needs pyzmq build with libzmq >= 4.1.0')
def test_server_can_send_to_several_client():
    from pseud.utils import register_rpc
    server_id = b'server'
    endpoint = b'tcp://127.0.0.1:5000'

    server = make_one_server(server_id, security_plugin='plain')

    client1 = make_one_client(server_id, security_plugin='plain',
                              user_id=b'client1',
                              password=b'client1',
                              )
    client2 = make_one_client(server_id, security_plugin='plain',
                              user_id=b'client2',
                              password=b'client2',
                              )

    server.bind(endpoint)
    client1.connect(endpoint)
    client2.connect(endpoint)
    server.start()
    client1.start()
    client2.start()

    register_rpc(name='string.lower')(str.lower)
    client1.string.lower('TATA').get()
    client2.string.lower('TATA').get()

    future1 = server.send_to(b'client1').string.lower('SCREAM1')

    future2 = server.send_to(b'client2').string.lower('SCREAM2')

    assert future1.get() == 'scream1'
    assert future2.get() == 'scream2'
    client1.stop()
    client2.stop()
    server.stop()


def test_raises_if_module_not_found():
    from pseud.interfaces import ServiceNotFoundError
    server_id = b'server'
    endpoint = b'inproc://here'
    server = make_one_server(server_id)

    client = make_one_client(server_id)
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

    server1 = make_one_server(b'server1')
    server2 = make_one_server(b'server2',
                              proxy_to=server1)

    client1 = make_one_client(b'server1')
    client2 = make_one_client(b'server2')

    server1.bind(b'inproc://server1')
    server2.bind(b'inproc://server2')
    client1.connect(b'inproc://server1')
    client2.connect(b'inproc://server2')
    server1.start()
    server2.start()

    # Local registration
    server1.register_rpc(name='str.lower')(str.lower)

    # Global registration
    register_rpc(name='str.upper')(str.upper)

    # local registration only to proxy
    server2.register_rpc(name='bla.lower')(str.lower)

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


def test_server_run_async_rpc():
    server = make_one_server(b'server')
    server.bind(b'inproc://server')
    server.start()

    client = make_one_client(b'server')
    client.connect(b'inproc://server')

    @server.register_rpc
    def aysnc_task():
        gevent.sleep(.1)
        return True

    future = client.aysnc_task()
    assert future.get() is True


def test_timeout_and_error_received_later(capsys):
    """
    capsys is comming from pytest magic
    http://pytest.org/latest/capture.html
    """
    server_id = b'server'
    endpoint = b'inproc://here'
    server = make_one_server(server_id)

    client = make_one_client(server_id)
    server.bind(endpoint)
    client.connect(endpoint)
    future = client.string.doesnotexists('QWERTY')
    future.set_exception(Timeout)
    gevent.sleep(.01)
    # at this point the future is not in the pool of futures,
    # thought we will still received the answer from the server
    assert not client.future_pool
    # gevent print exceptions that are not raised within its own green thread
    # so we capture stderr and check the exceptions is trigerred and not silent
    server.start()
    gevent.sleep(.01)
    out, err = capsys.readouterr()
    assert 'ServiceNotFoundError' in err
    with pytest.raises(Timeout):
        future.get()
    server.stop()
    client.close()


@pytest.mark.skipif((zmq.zmq_version_info() < (4, 1, 0) or
                     zmq.pyzmq_version_info() < (14, 4)),
                    reason='Needs pyzmq build with libzmq >= 4.1.0')
def test_client_can_reconnect():
    server_id = b'server'
    endpoint = b'tcp://127.0.0.1:8989'

    server = make_one_server(server_id)

    client = make_one_client(server_id)

    server.bind(endpoint)
    server.start()

    client.connect(endpoint)

    register_rpc(name='string.upper')(str.upper)

    future = client.string.upper('hello')
    assert future.get() == 'HELLO'

    client.disconnect(endpoint)
    client.connect(endpoint)
    gevent.sleep(.1)
    future = client.string.upper('hello')
    assert future.get() == 'HELLO'

    client.stop()
    server.stop()
