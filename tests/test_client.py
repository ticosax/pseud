import asyncio
import uuid

import pytest
import zmq.asyncio


def make_one_server_socket(identity, endpoint):
    context = zmq.asyncio.Context.instance()
    socket = context.socket(zmq.ROUTER)
    socket.setsockopt(zmq.IDENTITY, identity)
    socket.bind(endpoint)
    return socket


def make_one_client(peer_routing_id, user_id=None, timeout=5, loop=None, registry=None):
    from pseud import Client

    client = Client(
        peer_routing_id, user_id=user_id, timeout=timeout, loop=loop, registry=registry
    )
    return client


def test_client_creation():
    from pseud import Client

    peer_routing_id = b'echo'
    client = Client(peer_routing_id)
    assert client.peer_routing_id == peer_routing_id
    assert client.security_plugin == 'noop_auth_backend'


@pytest.mark.asyncio
async def test_client_can_bind():
    from pseud import Client

    endpoint = f'ipc://{__name__}'.encode()
    peer_routing_id = b'echo'
    client = Client(peer_routing_id)
    client.bind(endpoint)
    await client.stop()


@pytest.mark.asyncio
async def test_client_can_connect():
    from pseud import Client

    endpoint = f'ipc://{__name__}'.encode()
    peer_routing_id = b'echo'
    client = Client(peer_routing_id)
    client.connect(endpoint)
    await client.stop()


@pytest.mark.asyncio
async def test_client_method_wrapper(loop):
    from pseud.common import AttributeWrapper

    endpoint = 'ipc://test_client_method_wrapper'
    peer_routing_id = b'echo'
    client = make_one_client(peer_routing_id, loop=loop, timeout=0.1)
    method_name = 'a.b.c.d'
    with pytest.raises(RuntimeError):
        # If not connected can not call anything
        wrapper = getattr(client, method_name)
    client.connect(endpoint)
    async with client:
        wrapper = getattr(client, method_name)
        assert isinstance(wrapper, AttributeWrapper)
        assert wrapper._part_names == method_name.split('.')
        assert wrapper.name == method_name
        with pytest.raises(asyncio.TimeoutError):
            await wrapper()


@pytest.mark.asyncio
async def test_job_executed(loop, unused_tcp_port):
    from pseud.interfaces import OK, VERSION, WORK
    from pseud.packer import Packer

    peer_routing_id = b'echo'
    endpoint = f'tcp://127.0.0.1:{unused_tcp_port}'
    socket = make_one_server_socket(peer_routing_id, endpoint)
    client = make_one_client(peer_routing_id, loop=loop)
    client.connect(endpoint)

    async with client:
        probing = await socket.recv_multipart()
        assert len(probing) == 2
        future = asyncio.ensure_future(client.please.do_that_job(1, 2, 3, b=4))
        request = await socket.recv_multipart()
        client_routing_id, delimiter, version, uid, message_type, message = request
        assert delimiter == b''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = Packer().unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == (1, 2, 3)
        assert kw == {'b': 4}
        reply = [client_routing_id, b'', version, uid, OK, Packer().packb(True)]
        await socket.send_multipart(reply)
        result = await future
        assert result is True
        assert not client.future_pool


@pytest.mark.asyncio
async def test_job_server_never_reply(loop):
    from pseud.interfaces import VERSION, WORK
    from pseud.packer import Packer

    peer_routing_id = b'echo'
    endpoint = 'ipc://test_job_server_never_reply'
    socket = make_one_server_socket(peer_routing_id, endpoint)
    client = make_one_client(peer_routing_id, timeout=1, loop=loop)
    client.connect(endpoint)

    async with client:
        probing = await socket.recv_multipart()
        assert len(probing) == 2
        future = asyncio.ensure_future(client.please.do_that_job(1, 2, 3, b=4))
        await asyncio.sleep(0.1)
        request = await socket.recv_multipart()
        _, delimiter, version, uid, message_type, message = request
        assert delimiter == b''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = Packer().unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == (1, 2, 3)
        assert kw == {'b': 4}
        with pytest.raises(asyncio.TimeoutError):
            await future
        assert not client.future_pool


def test_client_registry():
    from pseud.utils import create_local_registry, get_rpc_callable

    user_id = b'client'
    peer_routing_id = b'echo'
    registry = create_local_registry(user_id)
    client = make_one_client(peer_routing_id, user_id=user_id, registry=registry)

    @client.register_rpc
    def foo():
        return 'bar'

    assert get_rpc_callable(name='foo', registry=client.registry)() == 'bar'
