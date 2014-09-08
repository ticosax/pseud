import uuid

import pytest
gevent = pytest.importorskip('gevent')
from gevent.timeout import Timeout
import zmq.green as zmq


def test_client_creation():
    from pseud._gevent import Client
    peer_identity = b'echo'
    client = Client(peer_identity)
    assert client.peer_routing_id == peer_identity
    assert client.security_plugin == 'noop_auth_backend'


def test_client_can_bind():
    from pseud import Client
    endpoint = b'tcp://127.0.0.1:5000'
    peer_identity = b'echo'
    client = Client(peer_identity)
    client.bind(endpoint)
    client.stop()


def test_client_can_connect():
    from pseud import Client
    endpoint = b'tcp://127.0.0.1:5000'
    peer_identity = b'echo'
    client = Client(peer_identity)
    client.connect(endpoint)
    client.stop()


def make_one_server_socket(identity, endpoint):
    context = zmq.Context.instance()
    router_sock = context.socket(zmq.ROUTER)
    router_sock.identity = identity
    port = router_sock.bind_to_random_port(endpoint)
    gevent.sleep(.1)
    return port, router_sock


def make_one_client(peer_identity, timeout=5, registry=None):
    from pseud._gevent import Client
    client = Client(peer_identity,
                    timeout=timeout,
                    registry=registry)
    return client


def test_client_method_wrapper():
    from pseud.common import AttributeWrapper
    endpoint = 'inproc://{}'.format(__name__).encode()
    peer_identity = b'echo'
    client = make_one_client(peer_identity)
    method_name = 'a.b.c.d'
    with pytest.raises(RuntimeError):
        # If not connected can not call anything
        wrapper = getattr(client, method_name)
    client.connect(endpoint)
    client.start()
    wrapper = getattr(client, method_name)
    assert isinstance(wrapper, AttributeWrapper)
    assert wrapper._part_names == method_name.split('.')
    assert wrapper.name == method_name
    with pytest.raises(Timeout):
        future = wrapper()
        future.get(timeout=.2)
    client.stop()


def test_job_executed():
    from pseud.common import msgpack_packb, msgpack_unpackb
    from pseud.interfaces import EMPTY_DELIMITER, OK, VERSION, WORK
    peer_identity = b'echo'
    endpoint = 'tcp://127.0.0.1'
    port, socket = make_one_server_socket(peer_identity, endpoint)

    client = make_one_client(peer_identity)
    client.connect('{}:{}'.format(endpoint, port).encode())

    future = client.please.do_that_job(1, 2, 3, b=4)
    request = gevent.spawn(socket.recv_multipart).get()
    routing_id, delimiter, version, uid, message_type, message = request
    assert delimiter == EMPTY_DELIMITER
    assert version == VERSION
    assert uid
    # check it is a real uuid
    uuid.UUID(bytes=uid)
    assert message_type == WORK
    locator, args, kw = msgpack_unpackb(message)
    assert locator == 'please.do_that_job'
    assert args == [1, 2, 3]
    assert kw == {'b': 4}
    reply = [routing_id, EMPTY_DELIMITER, version,
             uid, OK, msgpack_packb(True)]
    gevent.spawn(socket.send_multipart, reply)
    assert future.get() is True
    assert not client.future_pool
    client.stop()
    socket.close()


def test_job_server_never_reply():
    from pseud.common import msgpack_unpackb
    from pseud.interfaces import EMPTY_DELIMITER, VERSION, WORK
    peer_identity = b'echo'
    endpoint = 'tcp://127.0.0.1'
    port, socket = make_one_server_socket(peer_identity, endpoint)
    client = make_one_client(peer_identity,
                             timeout=.5)
    client.connect('{}:{}'.format(endpoint, port).encode())

    future = client.please.do_that_job(1, 2, 3, b=4)
    request = gevent.spawn(socket.recv_multipart).get()
    server_id, delimiter, version, uid, message_type, message = request
    assert delimiter == EMPTY_DELIMITER
    assert version == VERSION
    assert uid
    # check it is a real uuid
    uuid.UUID(bytes=uid)
    assert message_type == WORK
    locator, args, kw = msgpack_unpackb(message)
    assert locator == 'please.do_that_job'
    assert args == [1, 2, 3]
    assert kw == {'b': 4}
    with pytest.raises(Timeout):
        assert future.get()
    assert not client.future_pool
    client.stop()
    socket.close()


def test_client_registry():
    from pseud.utils import create_local_registry, get_rpc_callable
    identity = b'client0'
    peer_identity = b'echo'
    registry = create_local_registry(identity)
    client = make_one_client(peer_identity,
                             registry=registry)

    @client.register_rpc
    def foo():
        return 'bar'

    assert get_rpc_callable(name='foo', registry=client.registry)() == 'bar'
