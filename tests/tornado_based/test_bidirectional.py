from concurrent.futures import TimeoutError
import pytest
import tornado.testing
from zmq.eventloop import ioloop

ioloop.install()


class ClientTestCase(tornado.testing.AsyncTestCase):
    timeout = 2

    def make_one_server(self, identity, proxy_to=None):
        from pseud import Server
        server = Server(identity, proxy_to=proxy_to,
                        io_loop=self.io_loop)
        return server

    def make_one_client(self, identity, peer_identity):
        from pseud import Client
        client = Client(peer_identity,
                        identity=identity,
                        io_loop=self.io_loop)
        return client

    @tornado.testing.gen_test
    def test_client_can_send(self):
        from pseud.utils import register_rpc

        client_id = 'client'
        server_id = 'server'
        endpoint = 'inproc://here'

        server = self.make_one_server(server_id)

        client = self.make_one_client(client_id, server_id)

        server.bind(endpoint)
        yield server.start()

        client.connect(endpoint)

        import string
        register_rpc(name='string.upper')(string.upper)

        future = client.string.upper('hello')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result() == 'HELLO'
        client.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_server_can_send(self):
        from pseud.utils import register_rpc

        client_id = 'client'
        server_id = 'server'
        endpoint = 'inproc://here'

        server = self.make_one_server(server_id)

        client = self.make_one_client(client_id, server_id)

        server.bind(endpoint)
        client.connect(endpoint)
        yield server.start()
        yield client.start()

        import string
        register_rpc(name='string.lower')(string.lower)

        future = server.send_to(client_id).string.lower('SCREAM')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result() == 'scream'
        client.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_server_can_send_to_several_client(self):
        from pseud.utils import register_rpc

        server_id = 'server'
        endpoint = 'inproc://here'

        server = self.make_one_server(server_id)

        client1 = self.make_one_client('client1', server_id)
        client2 = self.make_one_client('client2', server_id)

        server.bind(endpoint)
        client1.connect(endpoint)
        client2.connect(endpoint)
        client1.start()
        client2.start()
        server.start()

        import string
        register_rpc(name='string.lower')(string.lower)

        future1 = server.send_to('client1').string.lower('SCREAM1')

        future2 = server.send_to('client2').string.lower('SCREAM2')

        self.io_loop.add_future(future2, self.stop)
        self.wait()
        assert future1.result() == 'scream1'
        assert future2.result() == 'scream2'
        client1.stop()
        client2.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_raises_if_module_not_found(self):
        from pseud.interfaces import ServiceNotFoundError

        server_id = 'server'
        endpoint = 'inproc://here'
        server = self.make_one_server(server_id)

        client = self.make_one_client('client', server_id)
        server.bind(endpoint)
        client.connect(endpoint)
        server.start()

        future = client.string.doesnotexists('QWERTY')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        with pytest.raises(ServiceNotFoundError):
            future.result()
        server.close()
        client.close()

    @tornado.testing.gen_test
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

        future1 = client1.str.lower('SCREAM')
        future2 = client2.str.lower('SCREAM')
        future3 = client1.str.upper('whisper')
        future4 = client2.str.upper('whisper')
        future5 = client2.bla.lower('SCREAM')
        self.io_loop.add_future(future5, self.stop)
        self.wait()
        assert future1.result() == 'scream'
        assert future2.result() == 'scream'
        assert future3.result() == 'WHISPER'
        assert future4.result() == 'WHISPER'
        assert future5.result() == 'scream'

        client1.stop()
        client2.stop()
        server1.stop()
        server2.stop()

    @tornado.testing.gen_test
    def test_server_run_async_rpc(self):
        from pseud._tornado import async_sleep
        server = self.make_one_server('server')
        server.bind('inproc://server')
        server.start()

        client = self.make_one_client('client', 'server')
        client.connect('inproc://server')

        @server.register_rpc
        @tornado.gen.coroutine
        def aysnc_task():
            yield async_sleep(self.io_loop, .01)
            raise tornado.gen.Return(True)

        future = client.aysnc_task()

        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result() is True

    @tornado.testing.gen_test
    def test_timeout_and_error_received_later(self):
        from pseud._tornado import async_sleep

        server_id = 'server'
        endpoint = 'inproc://here'
        server = self.make_one_server(server_id)

        client = self.make_one_client('client', server_id)
        server.bind(endpoint)
        client.connect(endpoint)

        future = client.string.doesnotexists('QWERTY')
        future.set_exception(TimeoutError)
        yield async_sleep(self.io_loop, .01)
        # at this point the future is not in the pool of futures,
        # thought we will still received the answer from the server
        assert not client.future_pool

        server.close()
        client.close()
