import asyncio

import pytest


def make_one_server(user_id, loop, proxy_to=None, security_plugin='noop_auth_backend'):
    from pseud import Server

    server = Server(
        user_id, proxy_to=proxy_to, security_plugin=security_plugin, loop=loop
    )
    return server


def make_one_client(
    peer_routing_id,
    loop,
    user_id=None,
    password=None,
    security_plugin='noop_auth_backend',
):
    from pseud import Client

    client = Client(
        peer_routing_id,
        user_id=user_id,
        password=password,
        security_plugin=security_plugin,
        loop=loop,
    )
    return client


@pytest.mark.asyncio
async def test_client_can_send(loop):
    from pseud.utils import register_rpc

    server_id = b'server'
    endpoint = b'inproc://here'

    server = make_one_server(server_id, loop)

    client = make_one_client(server_id, loop)

    server.bind(endpoint)
    client.connect(endpoint)
    register_rpc(name='string.upper')(str.upper)
    async with server, client:
        result = await client.string.upper('hello')
        assert result == 'HELLO'


@pytest.mark.asyncio
async def test_server_can_send(loop, unused_tcp_port, plain_auth_backend):
    from pseud.utils import register_rpc

    server_id = b'server'
    endpoint = f'tcp://127.0.0.1:{unused_tcp_port}'

    server = make_one_server(server_id, loop, security_plugin='plain')

    client = make_one_client(
        server_id, loop, user_id=b'alice', password=b'alice', security_plugin='plain'
    )

    server.bind(endpoint)
    client.connect(endpoint)
    register_rpc(name='string.lower')(str.lower)
    async with server, client:
        await asyncio.sleep(0.1)
        result = await server.send_to(b'alice').string.lower('SCREAM')
        assert result == 'scream'


@pytest.mark.asyncio
async def test_server_can_send_to_several_client(loop, unused_tcp_port):
    from pseud.utils import register_rpc

    server_id = b'server'
    endpoint = f'tcp://127.0.0.1:{unused_tcp_port}'

    server = make_one_server(server_id, loop, security_plugin='plain')

    client1 = make_one_client(
        server_id, loop, user_id=b'alice', password=b'alice', security_plugin='plain'
    )
    client2 = make_one_client(
        server_id, loop, user_id=b'bob', password=b'bob', security_plugin='plain'
    )

    server.bind(endpoint)
    client1.connect(endpoint)
    client2.connect(endpoint)
    register_rpc(name='string.lower')(str.lower)
    async with server, client1, client2:
        await asyncio.sleep(0.1)
        result1 = await server.send_to(b'alice').string.lower('SCREAM1')
        result2 = await server.send_to(b'bob').string.lower('SCREAM2')
        assert result1 == 'scream1'
        assert result2 == 'scream2'


@pytest.mark.asyncio
async def test_raises_if_module_not_found(loop):
    from pseud.interfaces import ServiceNotFoundError

    server_id = b'server'
    endpoint = b'inproc://here'
    server = make_one_server(server_id, loop)

    client = make_one_client(server_id, loop)
    server.bind(endpoint)
    client.connect(endpoint)
    async with server, client:
        with pytest.raises(ServiceNotFoundError):
            await client.string.doesnotexists('QWERTY')


@pytest.mark.asyncio
async def test_server_can_proxy_another_server(loop):
    """
    Client1 --> Server1.string.lower()
    Client2 --> Server2(Server1.string.lower())
    """
    from pseud.interfaces import ServiceNotFoundError
    from pseud.utils import get_rpc_callable, register_rpc

    server1 = make_one_server(b'server1', loop)
    server2 = make_one_server(b'server2', loop, proxy_to=server1)

    client1 = make_one_client(b'server1', loop)
    client2 = make_one_client(b'server2', loop)

    server1.bind(b'inproc://server1')
    server2.bind(b'inproc://server2')
    client1.connect(b'inproc://server1')
    client2.connect(b'inproc://server2')

    # Local registration
    server1.register_rpc(name='str.lower')(str.lower)

    # Global registration
    register_rpc(name='str.upper')(str.upper)

    # local registration only to proxy
    server2.register_rpc(name='bla.lower')(str.lower)
    async with server1, server2, client1, client2:

        with pytest.raises(ServiceNotFoundError):
            get_rpc_callable('str.lower', registry=server2.registry)

        with pytest.raises(ServiceNotFoundError):
            get_rpc_callable('bla.lower', registry=server1.registry)

        with pytest.raises(ServiceNotFoundError):
            get_rpc_callable('bla.lower')

        with pytest.raises(ServiceNotFoundError):
            assert get_rpc_callable('str.lower')

        assert get_rpc_callable('str.lower', registry=server1.registry)('L') == 'l'

        result1 = await client1.str.lower('SCREAM')
        result2 = await client2.str.lower('SCREAM')
        result3 = await client1.str.upper('whisper')
        result4 = await client2.str.upper('whisper')
        result5 = await client2.bla.lower('SCREAM')
        assert result1 == 'scream'
        assert result2 == 'scream'
        assert result3 == 'WHISPER'
        assert result4 == 'WHISPER'
        assert result5 == 'scream'


@pytest.mark.asyncio
async def test_server_run_async_rpc(loop):
    server = make_one_server(b'server', loop)
    server.bind(b'inproc://server')

    client = make_one_client(b'server', loop)
    client.connect(b'inproc://server')

    @server.register_rpc
    async def aysnc_task():
        await asyncio.sleep(0.01)
        return True

    async with server, client:
        result = await client.aysnc_task()
        assert result is True


@pytest.mark.asyncio
async def test_timeout_and_error_received_later(loop):
    server_id = b'server'
    endpoint = b'inproc://here'
    server = make_one_server(server_id, loop)
    client = make_one_client(server_id, loop)
    server.bind(endpoint)
    client.connect(endpoint)

    asyncio.ensure_future(client.string.doesnotexists('QWERTY'), loop=loop)
    for future in client.future_pool.values():
        future.set_exception(asyncio.TimeoutError)
    # at this point the future is not in the pool of futures,
    # thought we will still received the answer from the server
    assert not client.future_pool

    await server.stop()
    await client.stop()


@pytest.mark.asyncio
async def test_client_can_reconnect(loop, unused_tcp_port):
    from pseud.utils import register_rpc

    server_id = b'server'
    endpoint = f'tcp://127.0.0.1:{unused_tcp_port}'

    server = make_one_server(server_id, loop)
    client = make_one_client(server_id, loop)

    server.bind(endpoint)
    client.connect(endpoint)
    register_rpc(name='string.upper')(str.upper)
    async with server:
        result = await client.string.upper('hello')
        assert result == 'HELLO'

        client.disconnect(endpoint)
        client.connect(endpoint)

        await asyncio.sleep(0.1)
        result = await client.string.upper('hello')
        assert result == 'HELLO'
