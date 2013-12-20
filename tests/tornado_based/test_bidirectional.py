import pytest
import tornado.testing
from zmq.eventloop import ioloop

ioloop.install()


class ClientTestCase(tornado.testing.AsyncTestCase):
    timeout = 2

    def make_one_server(self, identity, io_loop=None):
        from pseud import Server
        from pseud import auth, heartbeat, predicate  # NOQA
        server = Server(identity, io_loop=io_loop)
        return server

    def make_one_client(self, identity, peer_identity, io_loop=None):
        from pseud import Client
        from pseud import auth, heartbeat, predicate  # NOQA
        client = Client(identity, peer_identity,
                        io_loop=io_loop)
        return client

    @tornado.testing.gen_test
    def test_client_can_send(self):
        from pseud.utils import register_rpc

        client_id = 'client'
        server_id = 'server'
        endpoint = 'inproc://here'

        server = self.make_one_server(server_id, io_loop=self.io_loop)

        client = self.make_one_client(client_id, server_id,
                                      io_loop=self.io_loop)

        server.bind(endpoint)
        yield server.start()

        client.connect(endpoint)

        import string
        register_rpc(name='string.upper')(string.upper)

        future = yield client.string.upper('hello')
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        assert future.result(timeout=self.timeout) == 'HELLO'
        client.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_server_can_send(self):
        from pseud.utils import peer_identity_provider
        from pseud.utils import register_rpc

        client_id = 'client'
        server_id = 'server'
        endpoint = 'inproc://here'

        server = self.make_one_server(server_id, io_loop=self.io_loop)

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

        import string
        register_rpc(name='string.lower')(string.lower)

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
        from pseud.utils import peer_identity_provider
        from pseud.utils import register_rpc

        server_id = 'server'
        endpoint = 'inproc://here'

        server = self.make_one_server(server_id, io_loop=self.io_loop)

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

        import string
        register_rpc(name='string.lower')(string.lower)

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
        from pseud.interfaces import ServiceNotFoundError

        server_id = 'server'
        endpoint = 'inproc://here'
        server = self.make_one_server(server_id, io_loop=self.io_loop)

        client = self.make_one_client('client', server_id,
                                      io_loop=self.io_loop)
        server.bind(endpoint)
        client.connect(endpoint)
        yield server.start()
        yield client.start()

        future = yield client.string.doesnotexists('QWERTY')
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.stop)
        self.wait()
        with pytest.raises(ServiceNotFoundError):
            future.result()
        server.close()
        client.close()

    def test_server_can_proxy_another_server(self):
        """
        Client1 --> Server1.string.lower()
        Client2 --> Server2(Server1.string.lower())
        """
        from pseud.interfaces import ServiceNotFoundError
        from pseud.utils import get_rpc_callable, register_rpc

        server1 = self.make_one_server('server1')
        server2 = self.make_one_server('server2', proxy_to=server1)

        client1 = self.make_one_client('client1', 'server1')
        client2 = self.make_one_client('client2', 'server2')

        server1.bind('inproc://server1')
        server2.bind('inproc://server2')
        client1.connect('inproc://server1')
        client2.connect('inproc://server2')
        server1.start()
        server2.start()

        import string
        # Local registration
        server1.register_rpc(name='str.lower')(string.lower)

        # Global registration
        register_rpc(name='str.upper')(string.upper)

        # local registration only to proxy
        server2.register_rpc(name='bla.lower')(string.lower)

        with pytest.raises(ServiceNotFoundError):
            get_rpc_callable('str.lower', registry=server2.registry)

        with pytest.raises(ServiceNotFoundError):
            get_rpc_callable('bla.lower', registry=server1.registry)

        with pytest.raises(ServiceNotFoundError):
            get_rpc_callable('bla.lower')

        with pytest.raises(ServiceNotFoundError):
            assert get_rpc_callable('str.lower')

        assert get_rpc_callable('str.lower',
                                registry=server1.registry)('L') == 'l'

        future1 = yield client1.str.lower('SCREAM')
        future2 = yield client2.str.lower('SCREAM')
        future3 = yield client1.str.upper('whisper')
        future4 = yield client2.str.upper('whisper')
        future5 = yield client2.bla.lower('SCREAM').get() == 'scream'
        assert future1.result() == 'scream'
        assert future2.result() == 'scream'
        assert future3.result() == 'WHISPER'
        assert future4.result() == 'WHISPER'
        assert future5.result() == 'scream'

        client1.stop()
        client2.stop()
        server1.stop()
        server2.stop()
