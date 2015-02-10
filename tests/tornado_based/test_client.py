import uuid

from concurrent.futures import TimeoutError
import pytest
import tornado.testing
import zmq
from zmq.eventloop import ioloop, zmqstream


ioloop.install()


def test_client_creation():
    from pseud import Client
    peer_routing_id = b'echo'
    client = Client(peer_routing_id)
    assert client.peer_routing_id == peer_routing_id
    assert client.security_plugin == 'noop_auth_backend'


def test_client_can_bind():
    from pseud import Client
    endpoint = 'ipc://{}'.format(__name__).encode()
    peer_routing_id = b'echo'
    client = Client(peer_routing_id)
    client.bind(endpoint)
    client.stop()


def test_client_can_connect():
    from pseud import Client
    endpoint = 'ipc://{}'.format(__name__).encode()
    peer_routing_id = b'echo'
    client = Client(peer_routing_id)
    client.connect(endpoint)
    client.stop()


class ClientTestCase(tornado.testing.AsyncTestCase):

    def make_one_server_socket(self, identity, endpoint):
        context = zmq.Context.instance()
        router_sock = context.socket(zmq.ROUTER)
        router_sock.identity = identity
        router_sock.bind(endpoint)
        return router_sock

    def make_one_client(self, peer_routing_id, user_id=None, timeout=5,
                        io_loop=None, registry=None):
        from pseud import Client
        client = Client(peer_routing_id,
                        user_id=user_id,
                        timeout=timeout,
                        io_loop=io_loop,
                        registry=registry)
        return client

    @tornado.testing.gen_test
    def test_client_method_wrapper(self):
        from pseud.common import AttributeWrapper
        endpoint = 'ipc://{}'.format(__name__).encode()
        peer_routing_id = b'echo'
        client = self.make_one_client(peer_routing_id,
                                      io_loop=self.io_loop)
        method_name = 'a.b.c.d'
        with pytest.raises(RuntimeError):
            # If not connected can not call anything
            wrapper = getattr(client, method_name)
        client.connect(endpoint)
        yield client.start()
        wrapper = getattr(client, method_name)
        assert isinstance(wrapper, AttributeWrapper)
        assert wrapper._part_names == method_name.split('.')
        assert wrapper.name == method_name
        with pytest.raises(TimeoutError):
            future = wrapper()
            future.result(timeout=.1)
        client.stop()

    @tornado.testing.gen_test
    def test_job_executed(self):
        from pseud._tornado import async_sleep
        from pseud.interfaces import OK, VERSION, WORK
        from pseud.packer import Packer
        peer_routing_id = b'echo'
        endpoint = 'ipc://{}'.format(self.__class__.__name__).encode()
        socket = self.make_one_server_socket(peer_routing_id, endpoint)
        client = self.make_one_client(peer_routing_id,
                                      io_loop=self.io_loop)
        client.connect(endpoint)

        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        future = client.please.do_that_job(1, 2, 3, b=4)
        yield async_sleep(self.io_loop, .1)
        request = yield tornado.gen.Task(stream.on_recv)
        _, _ = request
        request = yield tornado.gen.Task(stream.on_recv)
        client_routing_id, delimiter, version, uid, message_type, message =\
            request
        assert delimiter == b''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = Packer().unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == (1, 2, 3)
        assert kw == {'b': 4}
        reply = [
            client_routing_id, b'', version, uid, OK, Packer().packb(True)]
        yield tornado.gen.Task(stream.send_multipart, reply)
        result = yield future
        assert result is True
        assert not client.future_pool
        client.stop()
        stream.close()

    @tornado.testing.gen_test
    def test_job_server_never_reply(self):
        from pseud._tornado import async_sleep
        from pseud.interfaces import VERSION, WORK
        from pseud.packer import Packer
        peer_routing_id = b'echo'
        endpoint = 'ipc://{}'.format(self.__class__.__name__).encode()
        socket = self.make_one_server_socket(peer_routing_id, endpoint)
        client = self.make_one_client(peer_routing_id,
                                      timeout=1,
                                      io_loop=self.io_loop)
        client.connect(endpoint)

        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)

        future = client.please.do_that_job(1, 2, 3, b=4)
        yield async_sleep(self.io_loop, .1)
        request = yield tornado.gen.Task(stream.on_recv)
        _, _ = request
        request = yield tornado.gen.Task(stream.on_recv)
        _, delimiter, version, uid, message_type, message = request
        assert delimiter == b''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = Packer().unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == (1, 2, 3)
        assert kw == {'b': 4}
        with pytest.raises(TimeoutError):
            yield future
        assert not client.future_pool
        client.stop()
        stream.close()

    def test_client_registry(self):
        from pseud.utils import create_local_registry, get_rpc_callable
        user_id = b'client'
        peer_routing_id = b'echo'
        registry = create_local_registry(user_id)
        client = self.make_one_client(peer_routing_id, user_id=user_id,
                                      registry=registry)

        @client.register_rpc
        def foo():
            return 'bar'

        assert get_rpc_callable(name='foo',
                                registry=client.registry)() == 'bar'
