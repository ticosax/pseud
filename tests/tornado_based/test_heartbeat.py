from __future__ import unicode_literals
import functools

import tornado.testing
import zmq
import zope.interface.verify
from zmq.eventloop import ioloop, zmqstream


ioloop.install()


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


class HeartbeatTestCase(tornado.testing.AsyncTestCase):

    def make_one_server(self, identity, endpoint,
                        heartbeat_plugin,
                        io_loop=None):
        from pseud import Server
        server = Server(identity, heartbeat_plugin=heartbeat_plugin,
                        io_loop=io_loop)
        return server

    def make_one_client(self, identity, peer_identity,
                        heartbeat_plugin,
                        io_loop=None):
        from pseud import Client
        client = Client(peer_identity,
                        identity=identity,
                        heartbeat_plugin=heartbeat_plugin,
                        io_loop=io_loop)
        return client

    def test_basic_heartbeating(self):
        client_id = b'client'
        server_id = b'server'
        endpoint = b'ipc://here'
        heartbeat_backend = 'testing_heartbeat_backend'

        server = self.make_one_server(
            server_id, endpoint,
            heartbeat_plugin=heartbeat_backend,
            io_loop=self.io_loop)

        client = self.make_one_client(client_id, server_id,
                                      heartbeat_plugin=heartbeat_backend,
                                      io_loop=self.io_loop)
        server.bind(endpoint)
        client.connect(endpoint)
        context = zmq.Context.instance()
        monitoring_socket = context.socket(zmq.SUB)
        monitoring_socket.setsockopt(zmq.SUBSCRIBE, b'')
        monitoring_socket.connect('ipc://testing_heartbeating_backend')
        stream = zmqstream.ZMQStream(monitoring_socket, io_loop=self.io_loop)
        started = server.start()
        client.start()
        self.io_loop.add_future(started, self.stop)
        self.wait()

        sink = []

        def collector(sink, message):
            sink.extend(message)

        stream.on_recv(functools.partial(collector, sink))

        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        assert len(sink) >= 10
        assert all([client_id == i for i in sink])
        monitoring_socket.close()
        client.stop()
        server.stop()

    def test_basic_heartbeating_with_disconnection(self):
        client_id = b'client'
        server_id = b'server'
        endpoint = b'ipc://here'
        heartbeat_backend = 'testing_heartbeat_backend'

        server = self.make_one_server(
            server_id, endpoint,
            heartbeat_plugin=heartbeat_backend,
            io_loop=self.io_loop)

        client = self.make_one_client(client_id, server_id,
                                      heartbeat_plugin=heartbeat_backend,
                                      io_loop=self.io_loop)
        server.bind(endpoint)
        client.connect(endpoint)
        context = zmq.Context.instance()
        monitoring_socket = context.socket(zmq.SUB)
        monitoring_socket.setsockopt(zmq.SUBSCRIBE, b'')
        monitoring_socket.connect('ipc://testing_heartbeating_backend')
        stream = zmqstream.ZMQStream(monitoring_socket, io_loop=self.io_loop)
        started = server.start()
        client.start()
        self.io_loop.add_future(started, self.stop)
        self.wait()

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
        assert b"Gone b'client'" in sink
        monitoring_socket.close()
        server.stop()
        client.stop()
