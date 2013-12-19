import gevent
import zmq.green as zmq
import zope.interface.verify

from pybidirpc import auth, heartbeat  # NOQA


def collector(sink, socket):
    gevent.sleep(.1)
    while True:
        message = socket.recv_multipart()
        sink.extend(message)


def test_noop_heartbeat_backend_client():
    from pybidirpc.heartbeat import NoOpHeartbeatBackendForClient
    from pybidirpc.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      NoOpHeartbeatBackendForClient)


def test_noop_heartbeat_backend_server():
    from pybidirpc.heartbeat import NoOpHeartbeatBackendForServer
    from pybidirpc.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      NoOpHeartbeatBackendForServer)


def test_testing_heartbeat_backend_client():
    from pybidirpc.heartbeat import TestingHeartbeatBackendForClient
    from pybidirpc.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      TestingHeartbeatBackendForClient)


def test_testing_heartbeat_backend_server():
    from pybidirpc.heartbeat import TestingHeartbeatBackendForServer
    from pybidirpc.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      TestingHeartbeatBackendForServer)


def make_one_server(identity, endpoint, heartbeat_plugin):
    from pybidirpc._gevent import Server
    from pybidirpc import predicate, auth , heartbeat  # NOQA
    server = Server(identity,
                    heartbeat_plugin=heartbeat_plugin)
    return server


def make_one_client(identity, peer_identity,
                    heartbeat_plugin):
    from pybidirpc._gevent import Client
    from pybidirpc import predicate, auth , heartbeat  # NOQA
    client = Client(identity, peer_identity,
                    heartbeat_plugin=heartbeat_plugin)
    return client


def test_basic_heartbeating():
    client_id = 'client'
    server_id = 'server'
    endpoint = 'inproc://here'
    heartbeat_backend = 'testing_heartbeat_backend'

    server = make_one_server(
        server_id, endpoint,
        heartbeat_plugin=heartbeat_backend)

    client = make_one_client(client_id, server_id,
                             heartbeat_plugin=heartbeat_backend)
    server.bind(endpoint)
    client.connect(endpoint)
    context = zmq.Context.instance()
    monitoring_socket = context.socket(zmq.SUB)
    monitoring_socket.setsockopt(zmq.SUBSCRIBE, '')
    monitoring_socket.connect('inproc://testing_heartbeating_backend')
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


def test_basic_heartbeating_with_disconnection():
    client_id = 'client'
    server_id = 'server'
    endpoint = 'inproc://here'
    heartbeat_backend = 'testing_heartbeat_backend'

    server = make_one_server(
        server_id, endpoint,
        heartbeat_plugin=heartbeat_backend)

    client = make_one_client(client_id, server_id,
                             heartbeat_plugin=heartbeat_backend)
    server.bind(endpoint)
    client.connect(endpoint)
    context = zmq.Context.instance()
    monitoring_socket = context.socket(zmq.SUB)
    monitoring_socket.setsockopt(zmq.SUBSCRIBE, '')
    monitoring_socket.connect('inproc://testing_heartbeating_backend')
    sink = []

    spawning = gevent.spawn(collector, sink, monitoring_socket)
    server.start()
    client.start()

    gevent.spawn_later(.5, client.stop)
    gevent.sleep(1)
    try:
        assert len(sink) < 10
        assert "Gone 'client'" in sink
    finally:
        monitoring_socket.close()
        client.stop()
        server.stop()
        spawning.kill()
