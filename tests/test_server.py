import os.path
import time

import pytest
import zmq

pytestmark = pytest.mark.asyncio


async def test_server_creation():
    from pseud import Server

    user_id = b'echo'
    server = Server(user_id)
    assert server.user_id == user_id
    assert server.security_plugin == 'noop_auth_backend'


async def test_server_can_bind():
    from pseud import Server

    user_id = b'echo'
    endpoint = 'inproc://{}'.format(__name__).encode()
    server = Server(user_id, security_plugin='noop_auth_backend')
    server.bind(endpoint)
    await server.stop()


async def test_server_can_connect():
    from pseud import Server

    user_id = b'echo'
    endpoint = b'tcp://127.0.0.1:5000'
    server = Server(user_id, security_plugin='noop_auth_backend')
    server.connect(endpoint)
    await server.stop()


def make_one_client_socket(endpoint):
    context = zmq.asyncio.Context.instance()
    socket = context.socket(zmq.ROUTER)
    socket.connect(endpoint)
    return socket


def make_one_server(user_id, endpoint, loop):
    from pseud import Server

    server = Server(user_id, loop=loop)
    server.bind(endpoint)
    return server


async def test_job_running(loop):
    from pseud.interfaces import EMPTY_DELIMITER, OK, VERSION, WORK
    from pseud.packer import Packer
    from pseud.utils import register_rpc

    user_id = b'echo'
    endpoint = 'inproc://test_job_running'

    @register_rpc
    def job_success(a, b, c, d=None):
        time.sleep(0.2)
        return True

    server = make_one_server(user_id, endpoint, loop)
    socket = make_one_client_socket(endpoint)
    work = Packer().packb(('job_success', (1, 2, 3), {'d': False}))
    await socket.send_multipart([user_id, EMPTY_DELIMITER, VERSION, b'', WORK, work])
    async with server:
        response = await socket.recv_multipart()
        assert response == [
            user_id,
            EMPTY_DELIMITER,
            VERSION,
            b'',
            OK,
            Packer().packb(True),
        ]


async def test_job_not_found(loop):
    import pseud
    from pseud.interfaces import EMPTY_DELIMITER, ERROR, VERSION, WORK
    from pseud.packer import Packer

    user_id = b'echo'
    endpoint = 'inproc://test_job_not_found'
    server = make_one_server(user_id, endpoint, loop)
    socket = make_one_client_socket(endpoint)
    work = Packer().packb(('thisIsNotAFunction', (), {}))
    async with server:
        await socket.send_multipart([user_id, EMPTY_DELIMITER, VERSION, b'', WORK, work])
        response = await socket.recv_multipart()
        assert response[:-1] == [user_id, EMPTY_DELIMITER, VERSION, b'', ERROR]
        klass, message, traceback = Packer().unpackb(response[-1])
        assert klass == 'ServiceNotFoundError'
        assert message == 'thisIsNotAFunction'
        # pseud.__file__ might ends with .pyc
        assert os.path.dirname(pseud.__file__) in traceback


async def test_job_raise(loop):
    from pseud.interfaces import ERROR, VERSION, WORK
    from pseud.packer import Packer
    from pseud.utils import register_rpc

    user_id = b'echo'
    endpoint = 'inproc://test_job_raise'

    @register_rpc
    def job_buggy(*args, **kw):
        raise ValueError('too bad')

    server = make_one_server(user_id, endpoint, loop)
    socket = make_one_client_socket(endpoint)
    work = Packer().packb(('job_buggy', (), {}))
    async with server:
        await socket.send_multipart([user_id, b'', VERSION, b'', WORK, work])
        response = await socket.recv_multipart()
        assert response[:-1] == [user_id, b'', VERSION, b'', ERROR]
        klass, message, traceback = Packer().unpackb(response[-1])
        assert klass == 'ValueError'
        assert message == 'too bad'
        assert __file__ in traceback
