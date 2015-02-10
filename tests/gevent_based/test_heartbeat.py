import pytest
gevent = pytest.importorskip('gevent')
import zmq.green as zmq  # NOQA
import zope.interface.verify  # NOQA


def collector(sink, socket):
    gevent.sleep(.1)
    while True:
        message = socket.recv_multipart()
        sink.extend(message)


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


def make_one_server(identity,
                    heartbeat_plugin,
                    security_plugin='noop_auth_backend'):
    from pseud._gevent import Server
    server = Server(identity,
                    heartbeat_plugin=heartbeat_plugin,
                    security_plugin=security_plugin)
    return server


def make_one_client(peer_identity,
                    heartbeat_plugin,
                    security_plugin='noop_auth_backend',
                    user_id=None,
                    password=None):
    from pseud._gevent import Client
    client = Client(peer_identity,
                    heartbeat_plugin=heartbeat_plugin,
                    security_plugin=security_plugin,
                    user_id=user_id,
                    password=password)
    return client


@pytest.mark.skipif(zmq.zmq_version_info() < (4, 1, 0),
                    reason='Needs pyzmq build with libzmq >= 4.1.0')
def test_basic_heartbeating():
    client_id = 'client'
    server_id = 'server'
    endpoint = 'ipc://here'
    heartbeat_backend = 'testing_heartbeat_backend'

    server = make_one_server(server_id, heartbeat_plugin=heartbeat_backend,
                             security_plugin='plain')

    client = make_one_client(server_id, heartbeat_plugin=heartbeat_backend,
                             security_plugin='plain',
                             user_id=client_id,
                             password=client_id)
    server.bind(endpoint)
    client.connect(endpoint)
    context = zmq.Context.instance()
    monitoring_socket = context.socket(zmq.SUB)
    monitoring_socket.setsockopt(zmq.SUBSCRIBE, '')
    monitoring_socket.connect('ipc://testing_heartbeating_backend')
    server.start()
    client.start()

    sink = []

    spawning = gevent.spawn(collector, sink, monitoring_socket)

    gevent.sleep(1)
    try:
        assert len(sink) >= 10
        assert all([client_id == i for i in sink])
    finally:
        monitoring_socket.close()
        client.stop()
        server.stop()
        spawning.kill()


@pytest.mark.skipif(zmq.zmq_version_info() < (4, 1, 0),
                    reason='Needs pyzmq build with libzmq >= 4.1.0')
def test_basic_heartbeating_with_disconnection():
    client_id = 'client'
    server_id = 'server'
    endpoint = 'ipc://here'
    heartbeat_backend = 'testing_heartbeat_backend'

    server = make_one_server(server_id, heartbeat_plugin=heartbeat_backend,
                             security_plugin='plain')

    client = make_one_client(server_id, heartbeat_plugin=heartbeat_backend,
                             security_plugin='plain',
                             user_id=client_id,
                             password=client_id)
    server.bind(endpoint)
    client.connect(endpoint)
    context = zmq.Context.instance()
    monitoring_socket = context.socket(zmq.SUB)
    monitoring_socket.setsockopt(zmq.SUBSCRIBE, '')
    monitoring_socket.connect('ipc://testing_heartbeating_backend')
    sink = []

    spawning = gevent.spawn(collector, sink, monitoring_socket)
    server.start()
    client.start()

    gevent.spawn_later(.5, client.stop)
    gevent.sleep(.7)
    try:
        assert len(sink) < 10
        assert "Gone b'client'" in sink
    finally:
        monitoring_socket.close()
        client.stop()
        server.stop()
        spawning.kill()
