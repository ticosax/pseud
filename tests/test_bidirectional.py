import tornado.testing
from zmq.eventloop import ioloop


ioloop.install()


class ClientTestCase(tornado.testing.AsyncTestCase):
    timeout = 2

    def make_one_server(self, identity, context_module_name, endpoint,
                        io_loop=None):
        from pyzmq_rpc import Server
        server = Server(identity, context_module_name, io_loop=io_loop)
        return server

    def make_one_client(self, identity, peer_identity, io_loop=None):
        from pyzmq_rpc import Client
        client = Client(identity, peer_identity, io_loop=io_loop)
        return client

    @tornado.testing.gen_test
    def test_client_can_send(self):
        client_id = 'client'
        server_id = 'server'
        endpoint = 'ipc://here'

        server = self.make_one_server(server_id, None, endpoint,
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
        future = yield client.string.upper('hello')
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        assert future.result(timeout=self.timeout
                             ).result(timeout=self.timeout) == 'HELLO'

    @tornado.testing.gen_test
    def test_server_can_send(self):
        client_id = 'client'
        server_id = 'server'
        endpoint = 'ipc://here'

        server = self.make_one_server(server_id, None, endpoint,
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

        # Bypass client registration for this test
        # hardcode identity of peer
        server.peer_identity = client_id
        future = yield server.string.lower('SCREAM')
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        assert future.result(timeout=self.timeout
                             ).result(timeout=self.timeout) == 'scream'
