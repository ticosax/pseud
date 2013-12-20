import uuid

from concurrent.futures import TimeoutError
import msgpack
import pytest
import tornado.testing
import zmq
from zmq.eventloop import ioloop, zmqstream


ioloop.install()


def test_client_creation():
    from pseud import Client
    from pseud import auth, heartbeat  # NOQA
    identity = __name__
    peer_identity = 'echo'
    client = Client(identity, peer_identity)
    assert client.peer_identity == peer_identity
    assert client.identity == identity
    assert client.security_plugin == 'noop_auth_backend'
    # assert client._timeout == 5000


def test_client_can_bind():
    from pseud import Client
    from pseud import auth, heartbeat  # NOQA
    endpoint = 'inproc://{}'.format(__name__)
    identity = __name__
    peer_identity = 'echo'
    client = Client(identity, peer_identity)
    client.bind(endpoint)
    client.stop()


def test_client_can_connect():
    from pseud import Client
    from pseud import auth, heartbeat  # NOQA
    endpoint = 'inproc://{}'.format(__name__)
    identity = __name__
    peer_identity = 'echo'
    client = Client(identity, peer_identity)
    client.connect(endpoint)
    client.stop()


class ClientTestCase(tornado.testing.AsyncTestCase):
    timeout = 2

    def make_one_server_socket(self, identity, endpoint):
        context = zmq.Context.instance()
        router_sock = context.socket(zmq.ROUTER)
        router_sock.identity = identity
        router_sock.bind(endpoint)
        return router_sock

    def make_one_client(self, identity, peer_identity, timeout=5,
                        io_loop=None, registry=None):
        from pseud import Client
        from pseud import auth, heartbeat, predicate  # NOQA
        client = Client(identity, peer_identity,
                        timeout=timeout,
                        io_loop=io_loop,
                        registry=registry)
        return client

    @tornado.testing.gen_test
    def test_client_method_wrapper(self):
        from pseud.common import AttributeWrapper
        from pseud import auth, heartbeat  # NOQA
        endpoint = 'inproc://{}'.format(__name__)
        identity = __name__
        peer_identity = 'echo'
        client = self.make_one_client(identity, peer_identity,
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
        self.io_loop.add_timeout(self.io_loop.time() + 1,
                                 self.io_loop.stop)
        with pytest.raises(TimeoutError):
            future = yield wrapper()
            self.io_loop.start()
            future.exception(timeout=.2)
        client.stop()

    @tornado.testing.gen_test
    def test_job_executed(self):
        from pseud.interfaces import OK, VERSION, WORK
        from pseud import auth, heartbeat  # NOQA
        identity = 'client0'
        peer_identity = 'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__)
        socket = self.make_one_server_socket(peer_identity, endpoint)
        client = self.make_one_client(identity, peer_identity,
                                      io_loop=self.io_loop)
        client.connect(endpoint)

        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        future = yield client.please.do_that_job(1, 2, 3, b=4)
        request = yield tornado.gen.Task(stream.on_recv)
        stream.stop_on_recv()
        server_id, delimiter, version, uid, message_type, message = request
        assert delimiter == ''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = msgpack.unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == [1, 2, 3]
        assert kw == {'b': 4}
        reply = [identity, '', version, uid, OK, msgpack.packb(True)]
        yield tornado.gen.Task(stream.send_multipart, reply)
        self.io_loop.add_timeout(self.io_loop.time() + .1,
                                 self.io_loop.stop)
        self.io_loop.start()
        assert future.result() is True
        assert not client.future_pool
        client.stop()

    @tornado.testing.gen_test
    def test_job_server_never_reply(self):
        from pseud.interfaces import VERSION, WORK
        from pseud import auth, heartbeat  # NOQA
        identity = 'client0'
        peer_identity = 'echo'
        endpoint = 'inproc://{}'.format(self.__class__.__name__)
        socket = self.make_one_server_socket(peer_identity, endpoint)
        client = self.make_one_client(identity, peer_identity,
                                      timeout=1,
                                      io_loop=self.io_loop)
        client.connect(endpoint)

        stream = zmqstream.ZMQStream(socket, io_loop=self.io_loop)
        future = yield client.please.do_that_job(1, 2, 3, b=4)
        request = yield tornado.gen.Task(stream.on_recv)
        stream.stop_on_recv()
        server_id, delimiter, version, uid, message_type, message = request
        assert delimiter == ''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = msgpack.unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == [1, 2, 3]
        assert kw == {'b': 4}
        self.io_loop.add_timeout(self.io_loop.time() + 1.1,
                                 self.io_loop.stop)
        self.io_loop.start()
        with pytest.raises(TimeoutError):
            assert future.result()
        assert not client.future_pool
        client.stop()

    def test_client_registry(self):
        from pseud.utils import create_local_registry, get_rpc_callable
        identity = 'client0'
        peer_identity = 'echo'
        registry = create_local_registry(identity)
        client = self.make_one_client(identity, peer_identity,
                                      registry=registry)

        @client.register_rpc
        def foo():
            return 'bar'

        assert get_rpc_callable(name='foo',
                                registry=client.registry)() == 'bar'
