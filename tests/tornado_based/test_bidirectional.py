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

    def make_one_server(self, user_id, proxy_to=None,
                        security_plugin='noop_auth_backend'):
        from pseud import Server
        server = Server(user_id, proxy_to=proxy_to,
                        security_plugin=security_plugin,
                        io_loop=self.io_loop)
        return server

    def make_one_client(self, peer_routing_id, user_id=None,
                        password=None, security_plugin='noop_auth_backend'):
        from pseud import Client
        client = Client(peer_routing_id,
                        user_id=user_id,
                        password=password,
                        security_plugin=security_plugin,
                        io_loop=self.io_loop)
        return client

    @tornado.testing.gen_test
    def test_client_can_send(self):
        from pseud.utils import register_rpc

        server_id = b'server'
        endpoint = b'inproc://here'

        server = self.make_one_server(server_id)

        client = self.make_one_client(server_id)

        server.bind(endpoint)
        yield server.start()

        client.connect(endpoint)
        yield client.start()

        register_rpc(name='string.upper')(str.upper)

        result = yield client.string.upper('hello')
        assert result == 'HELLO'
        client.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_server_can_send(self):
        from pseud.utils import register_rpc

        server_id = b'server'
        endpoint = b'tcp://127.0.0.1:5000'

        server = self.make_one_server(server_id, security_plugin='plain')

        client = self.make_one_client(server_id, user_id=b'alice',
                                      password=b'alice',
                                      security_plugin='plain')

        server.bind(endpoint)
        client.connect(endpoint)
        yield server.start()
        yield client.start()

        register_rpc(name='string.lower')(str.lower)
        yield client.string.lower('TATA')

        result = yield server.send_to(b'alice').string.lower('SCREAM')
        assert result == 'scream'
        client.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_server_can_send_to_several_client(self):
        from pseud.utils import register_rpc
        from pseud._tornado import async_sleep

        server_id = b'server'
        endpoint = b'tcp://127.0.0.1:5000'

        server = self.make_one_server(server_id, security_plugin='plain')

        client1 = self.make_one_client(server_id, user_id=b'alice',
                                       password=b'alice',
                                       security_plugin='plain')
        client2 = self.make_one_client(server_id, user_id=b'bob',
                                       password=b'bob',
                                       security_plugin='plain')

        server.bind(endpoint)
        yield server.start()
        client1.connect(endpoint)
        client2.connect(endpoint)
        yield client1.start()
        yield client2.start()

        register_rpc(name='string.lower')(str.lower)

        # call the server to register
        yield client1.string.lower('TATA')
        yield client2.string.lower('TATA')
        result1 = yield server.send_to(b'alice').string.lower('SCREAM1')

        result2 = yield server.send_to(b'bob').string.lower('SCREAM2')

        assert result1 == 'scream1'
        assert result2 == 'scream2'
        client1.stop()
        client2.stop()
        server.stop()

    @tornado.testing.gen_test
    def test_raises_if_module_not_found(self):
        from pseud.interfaces import ServiceNotFoundError

        server_id = b'server'
        endpoint = b'inproc://here'
        server = self.make_one_server(server_id)

        client = self.make_one_client(server_id)
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

        client1 = self.make_one_client(b'server1')
        client2 = self.make_one_client(b'server2')

        server1.bind(b'inproc://server1')
        server2.bind(b'inproc://server2')
        client1.connect(b'inproc://server1')
        client2.connect(b'inproc://server2')
        yield server1.start()
        yield server2.start()

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

        result1 = yield client1.str.lower('SCREAM')
        result2 = yield client2.str.lower('SCREAM')
        result3 = yield client1.str.upper('whisper')
        result4 = yield client2.str.upper('whisper')
        result5 = yield client2.bla.lower('SCREAM')
        assert result1 == 'scream'
        assert result2 == 'scream'
        assert result3 == 'WHISPER'
        assert result4 == 'WHISPER'
        assert result5 == 'scream'

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

        client = self.make_one_client(b'server')
        client.connect(b'inproc://server')

        @server.register_rpc
        @tornado.gen.coroutine
        def aysnc_task():
            yield async_sleep(self.io_loop, .01)
            raise tornado.gen.Return(True)

        result = yield client.aysnc_task()

        assert result is True

    @tornado.testing.gen_test
    def test_timeout_and_error_received_later(self):
        from pseud._tornado import async_sleep

        server_id = b'server'
        endpoint = b'inproc://here'
        server = self.make_one_server(server_id)

        client = self.make_one_client(server_id)
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

    @tornado.testing.gen_test
    def test_client_can_reconnect(self):
        from pseud.utils import register_rpc

        client_id = b'client'
        server_id = b'server'
        endpoint = b'tcp://127.0.0.1:8989'

        server = self.make_one_server(server_id)

        client = self.make_one_client(server_id)

        server.bind(endpoint)
        server.start()

        client.connect(endpoint)

        register_rpc(name='string.upper')(str.upper)

        result = yield client.string.upper('hello')
        assert result == 'HELLO'

        client.disconnect(endpoint)
        client.connect(endpoint)
        result = yield client.string.upper('hello')
        assert result == 'HELLO'

        client.stop()
        server.stop()
