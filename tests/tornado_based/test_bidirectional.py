from __future__ import unicode_literals

from concurrent.futures import TimeoutError
from future.builtins import str
import pytest
import tornado.testing
import zmq
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

        client_id = b'client'
        server_id = b'server'
        endpoint = b'inproc://here'

        server = self.make_one_server(server_id)

        client = self.make_one_client(client_id, server_id)

        server.bind(endpoint)
        yield server.start()

        client.connect(endpoint)

        register_rpc(name='string.upper')(str.upper)

        future = client.string.upper('hello')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result() == 'HELLO'
        client.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_server_can_send(self):
        from pseud.utils import register_rpc

        client_id = b'client'
        server_id = b'server'
        endpoint = b'inproc://here'

        server = self.make_one_server(server_id)

        client = self.make_one_client(client_id, server_id)

        server.bind(endpoint)
        client.connect(endpoint)
        yield server.start()
        yield client.start()

        register_rpc(name='string.lower')(str.lower)

        future = server.send_to(client_id).string.lower('SCREAM')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result() == 'scream'
        client.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_server_can_send_to_several_client(self):
        from pseud.utils import register_rpc

        server_id = b'server'
        endpoint = b'inproc://here'

        server = self.make_one_server(server_id)

        client1 = self.make_one_client(b'client1', server_id)
        client2 = self.make_one_client(b'client2', server_id)

        server.bind(endpoint)
        client1.connect(endpoint)
        client2.connect(endpoint)
        client1.start()
        client2.start()
        server.start()

        register_rpc(name='string.lower')(str.lower)

        future1 = server.send_to(b'client1').string.lower('SCREAM1')

        future2 = server.send_to(b'client2').string.lower('SCREAM2')

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

        server_id = b'server'
        endpoint = b'inproc://here'
        server = self.make_one_server(server_id)

        client = self.make_one_client(b'client', server_id)
        server.bind(endpoint)
        client.connect(endpoint)
        yield server.start()
        yield client.start()

        with pytest.raises(ServiceNotFoundError):
            yield client.string.doesnotexists('QWERTY')
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

        server1 = self.make_one_server(b'server1')
        server2 = self.make_one_server(b'server2', proxy_to=server1)

        client1 = self.make_one_client(b'client1', b'server1')
        client2 = self.make_one_client(b'client2', b'server2')

        server1.bind(b'inproc://server1')
        server2.bind(b'inproc://server2')
        client1.connect(b'inproc://server1')
        client2.connect(b'inproc://server2')
        server1.start()
        server2.start()

        # Local registration
        server1.register_rpc(name='str.lower')(str.lower)

        # Global registration
        register_rpc(name='str.upper')(str.upper)

        # local registration only to proxy
        server2.register_rpc(name='bla.lower')(str.lower)

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
        server = self.make_one_server(b'server')
        server.bind(b'inproc://server')
        server.start()

        client = self.make_one_client(b'client', b'server')
        client.connect(b'inproc://server')

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

        server_id = b'server'
        endpoint = b'inproc://here'
        server = self.make_one_server(server_id)

        client = self.make_one_client(b'client', server_id)
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

    @pytest.mark.skipif(zmq.zmq_version_info() < (4, 1, 0),
                        reason='Needs zeromq build with libzmq >= 4.1.0')
    def test_client_can_reconnect(self):
        from pseud.utils import register_rpc

        client_id = b'client'
        server_id = b'server'
        endpoint = b'tcp://127.0.0.1:8989'

        server = self.make_one_server(server_id)

        client = self.make_one_client(client_id, server_id)

        server.bind(endpoint)
        server.start()

        client.connect(endpoint)

        register_rpc(name='string.upper')(str.upper)

        future = client.string.upper('hello')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result() == 'HELLO'

        client.disconnect(endpoint)
        client.connect(endpoint)
        future = client.string.upper('hello')
        self.io_loop.add_future(future, self.stop)
        self.wait()
        assert future.result() == 'HELLO'

        client.stop()
        server.stop()
