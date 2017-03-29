import asyncio

import pytest
import zmq
import zope.interface.verify


def test_noop_heartbeat_backend_client():
    from pseud.heartbeat import NoOpHeartbeatBackendForClient
    from pseud.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      NoOpHeartbeatBackendForClient)


def test_noop_heartbeat_backend_server():
    from pseud.heartbeat import NoOpHeartbeatBackendForServer
    from pseud.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      NoOpHeartbeatBackendForServer)


def test_testing_heartbeat_backend_client():
    from pseud.heartbeat import TestingHeartbeatBackendForClient
    from pseud.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      TestingHeartbeatBackendForClient)


def test_testing_heartbeat_backend_server():
    from pseud.heartbeat import TestingHeartbeatBackendForServer
    from pseud.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      TestingHeartbeatBackendForServer)


def make_one_server(user_id, endpoint,
                    security_plugin='noop_auth_backend',
                    heartbeat_plugin=None,
                    loop=None):
    from pseud import Server
    server = Server(user_id, heartbeat_plugin=heartbeat_plugin,
                    security_plugin=security_plugin,
                    loop=loop)
    return server


def make_one_client(peer_routing_id,
                    security_plugin='noop_auth_backend',
                    heartbeat_plugin=None,
                    user_id=None,
                    password=None,
                    loop=None):
    from pseud import Client
    client = Client(peer_routing_id,
                    security_plugin=security_plugin,
                    heartbeat_plugin=heartbeat_plugin,
                    user_id=user_id,
                    password=password,
                    loop=loop)
    return client


@pytest.mark.asyncio
async def test_basic_heartbeating(loop):
    server_id = b'server'
    endpoint = b'ipc://here'
    heartbeat_backend = 'testing_heartbeat_backend'

    server = make_one_server(
        server_id, endpoint,
        security_plugin='plain',
        heartbeat_plugin=heartbeat_backend,
        loop=loop)

    client = make_one_client(server_id,
                             security_plugin='plain',
                             heartbeat_plugin=heartbeat_backend,
                             user_id=b'client',
                             password=b'client',
                             loop=loop)
    server.bind(endpoint)
    client.connect(endpoint)
    context = zmq.asyncio.Context.instance()
    monitoring_socket = context.socket(zmq.SUB)
    monitoring_socket.setsockopt(zmq.SUBSCRIBE, b'')
    monitoring_socket.connect('ipc://testing_heartbeating_backend')
    await server.start()
    await client.start()

    sink = []

    async def collector(sink):
        while True:
            sink.extend(await monitoring_socket.recv_multipart())

    task = loop.create_task(collector(sink))
    await asyncio.sleep(1.1)
    task.cancel()
    assert len(sink) >= 10
    assert all([b'client' == i for i in sink]), sink
    monitoring_socket.close()
    await client.stop()
    await server.stop()


@pytest.mark.asyncio
async def test_basic_heartbeating_with_disconnection(loop,
                                                     unused_tcp_port_factory):
    port = unused_tcp_port_factory()
    server_id = b'server'
    endpoint = f'tcp://127.0.0.1:{port}'
    heartbeat_backend = 'testing_heartbeat_backend'

    server = make_one_server(
        server_id, endpoint,
        security_plugin='plain',
        heartbeat_plugin=heartbeat_backend,
        loop=loop)

    client = make_one_client(server_id,
                             security_plugin='plain',
                             heartbeat_plugin=heartbeat_backend,
                             user_id=b'client',
                             password=b'client',
                             loop=loop)
    server.bind(endpoint)
    client.connect(endpoint)
    context = zmq.asyncio.Context.instance()
    monitoring_socket = context.socket(zmq.SUB)
    monitoring_socket.setsockopt(zmq.SUBSCRIBE, b'')
    monitoring_socket.connect('ipc://testing_heartbeating_backend')
    await server.start()
    await client.start()

    sink = []

    async def collector(sink):
        while True:
            sink.extend(await monitoring_socket.recv_multipart())

    task = loop.create_task(collector(sink))
    loop.call_later(.5, asyncio.ensure_future, client.stop())
    await asyncio.sleep(1.1)
    task.cancel()

    assert len(sink) < 10
    assert b"Gone client" in sink
    monitoring_socket.close()
    await server.stop()
    await client.stop()
