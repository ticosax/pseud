import pytest
import tornado.testing
from zmq.eventloop import ioloop

ioloop.install()


class ClientTestCase(tornado.testing.AsyncTestCase):
    timeout = 2

    def make_one_server(self, identity, context_module_name, endpoint,
                        io_loop=None):
        from pybidirpc import Server
        server = Server(identity, context_module_name,
                        io_loop=io_loop)
        return server

    def make_one_client(self, identity, peer_identity, io_loop=None):
        from pybidirpc import Client
        client = Client(identity, peer_identity,
                        io_loop=io_loop)
        return client

    @tornado.testing.gen_test
    def test_client_can_send(self):
        from pybidirpc import auth, heartbeat  # NOQA
        client_id = 'client'
        server_id = 'server'
        endpoint = 'inproc://here'

        server = self.make_one_server(server_id, '', endpoint,
                                      io_loop=self.io_loop)

        client = self.make_one_client(client_id, server_id,
                                      io_loop=self.io_loop)

        server.bind(endpoint)
        yield server.start()

        client.connect(endpoint)

        future = yield client.string.upper('hello')
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        assert future.result(timeout=self.timeout) == 'HELLO'
        client.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_server_can_send(self):
        from pybidirpc.utils import peer_identity_provider
        from pybidirpc import auth, heartbeat  # NOQA
        client_id = 'client'
        server_id = 'server'
        endpoint = 'inproc://here'

        server = self.make_one_server(server_id, '', endpoint,
                                      io_loop=self.io_loop)

        client = self.make_one_client(client_id, server_id,
                                      io_loop=self.io_loop)

        @tornado.gen.coroutine
        def bind_and_start(server, endpoint):
            server.bind(endpoint)
            yield server.start()

        @tornado.gen.coroutine
        def connect_and_start(client, endpoint):
            client.connect(endpoint)
            yield client.start()

        yield bind_and_start(server, endpoint)
        yield connect_and_start(client, endpoint)

        with peer_identity_provider(server, client_id):
            future = yield server.string.lower('SCREAM')

        # server.peer_identity = client_id
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        assert future.result(timeout=self.timeout) == 'scream'
        client.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_server_can_send_to_several_client(self):
        from pybidirpc.utils import peer_identity_provider
        from pybidirpc import auth, heartbeat  # NOQA
        server_id = 'server'
        endpoint = 'inproc://here'

        server = self.make_one_server(server_id, '', endpoint,
                                      io_loop=self.io_loop)

        client1 = self.make_one_client('client1', server_id,
                                       io_loop=self.io_loop)
        client2 = self.make_one_client('client2', server_id,
                                       io_loop=self.io_loop)

        server.bind(endpoint)
        client1.connect(endpoint)
        client2.connect(endpoint)
        yield server.start()
        yield client1.start()
        yield client2.start()

        with peer_identity_provider(server, 'client1'):
            future1 = yield server.string.lower('SCREAM1')

        with peer_identity_provider(server, 'client2'):
            future2 = yield server.string.lower('SCREAM2')

        # server.peer_identity = client_id
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        assert future1.result(timeout=self.timeout) == 'scream1'
        assert future2.result(timeout=self.timeout) == 'scream2'
        client1.stop()
        client2.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_raises_if_module_not_found(self):
        from pybidirpc import auth, heartbeat  # NOQA
        from pybidirpc.interfaces import ServiceNotFoundError
        server_id = 'server'
        endpoint = 'inproc://here'
        server = self.make_one_server(server_id, __name__, endpoint,
                                      io_loop=self.io_loop)

        client = self.make_one_client('client', server_id,
                                      io_loop=self.io_loop)
        server.bind(endpoint)
        client.connect(endpoint)
        yield server.start()
        yield client.start()
        future = yield client.string.lower('QWERTY')
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        with pytest.raises(ServiceNotFoundError):
            future.result()
        server.close()
        client.close()
