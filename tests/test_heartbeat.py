import functools

import tornado.testing
import zmq
import zope.interface.verify
from zmq.eventloop import ioloop, zmqstream

from pyzmq_rpc import auth
from pyzmq_rpc import heartbeat

ioloop.install()


def test_noop_heartbeat_backend_client():
    from pyzmq_rpc.heartbeat import NoOpHeartbeatBackendForClient
    from pyzmq_rpc.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      NoOpHeartbeatBackendForClient)


def test_noop_heartbeat_backend_server():
    from pyzmq_rpc.heartbeat import NoOpHeartbeatBackendForServer
    from pyzmq_rpc.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      NoOpHeartbeatBackendForServer)


def test_testing_heartbeat_backend_client():
    from pyzmq_rpc.heartbeat import TestingHeartbeatBackendForClient
    from pyzmq_rpc.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      TestingHeartbeatBackendForClient)


def test_testing_heartbeat_backend_server():
    from pyzmq_rpc.heartbeat import TestingHeartbeatBackendForServer
    from pyzmq_rpc.interfaces import IHeartbeatBackend

    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      TestingHeartbeatBackendForServer)


class HeartbeatTestCase(tornado.testing.AsyncTestCase):
    timeout = 2

    def make_one_server(self, identity, context_module_name, endpoint,
                        heartbeat_plugin,
                        io_loop=None):
        from pyzmq_rpc import Server
        server = Server(identity, context_module_name,
                        heartbeat_plugin=heartbeat_plugin,
                        io_loop=io_loop)
        return server

    def make_one_client(self, identity, peer_identity,
                        heartbeat_plugin,
                        io_loop=None):
        from pyzmq_rpc import Client
        client = Client(identity, peer_identity,
                        heartbeat_plugin=heartbeat_plugin,
                        io_loop=io_loop)
        return client

    @tornado.testing.gen_test
    def test_basic_heartbeating(self):
        client_id = 'client'
        server_id = 'server'
        endpoint = 'inproc://here'
        heartbeat_backend = 'testing_heartbeat_backend'

        server = self.make_one_server(
            server_id, None, endpoint,
            heartbeat_plugin=heartbeat_backend,
            io_loop=self.io_loop)

        client = self.make_one_client(client_id, server_id,
                                      heartbeat_plugin=heartbeat_backend,
                                      io_loop=self.io_loop)
        server.bind(endpoint)
        client.connect(endpoint)
        context = zmq.Context.instance()
        monitoring_socket = context.socket(zmq.SUB)
        monitoring_socket.setsockopt(zmq.SUBSCRIBE, '')
        monitoring_socket.connect('inproc://testing_heartbeating_backend')
        stream = zmqstream.ZMQStream(monitoring_socket, io_loop=self.io_loop)
        yield server.start()
        yield client.start()

        sink = []

        def collector(sink, message):
            sink.extend(message)

        stream.on_recv(functools.partial(collector, sink))

        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        assert len(sink) >= 10
        assert all([client_id == i for i in sink])
        yield client.stop()
        yield server.stop()

    @tornado.testing.gen_test
    def test_basic_heartbeating_with_disconnection(self):
        client_id = 'client'
        server_id = 'server'
        endpoint = 'inproc://here'
        heartbeat_backend = 'testing_heartbeat_backend'

        server = self.make_one_server(
            server_id, None, endpoint,
            heartbeat_plugin=heartbeat_backend,
            io_loop=self.io_loop)

        client = self.make_one_client(client_id, server_id,
                                      heartbeat_plugin=heartbeat_backend,
                                      io_loop=self.io_loop)
        server.bind(endpoint)
        client.connect(endpoint)
        context = zmq.Context.instance()
        monitoring_socket = context.socket(zmq.SUB)
        monitoring_socket.setsockopt(zmq.SUBSCRIBE, '')
        monitoring_socket.connect('inproc://testing_heartbeating_backend')
        stream = zmqstream.ZMQStream(monitoring_socket, io_loop=self.io_loop)
        yield server.start()
        yield client.start()

        sink = []

        def collector(sink, message):
            sink.extend(message)

        stream.on_recv(functools.partial(collector, sink))

        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.io_loop.add_timeout(self.io_loop.time() + .5,
                                 client.stop)
        self.wait()
        assert len(sink) < 10
        assert "Gone 'client'" in sink
        yield server.stop()
