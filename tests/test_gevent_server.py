import os.path
import time

import pytest
gevent = pytest.importorskip('gevent')
import zmq.green as zmq


def read_once(socket):
    return socket.recv_multipart()


def test_server_creation():
    from pseud._gevent import Server
    user_id = b'echo'
    server = Server(user_id)
    assert server.user_id == user_id
    assert server.security_plugin == 'noop_auth_backend'


def test_server_can_bind():
    from pseud._gevent import Server
    user_id = b'echo'
    endpoint = 'inproc://{}'.format(__name__).encode()
    server = Server(user_id,
                    security_plugin='noop_auth_backend')
    server.bind(endpoint)
    server.stop()


def test_server_can_connect():
    from pseud._gevent import Server
    user_id = b'echo'
    endpoint = b'tcp://127.0.0.1:5000'
    server = Server(user_id,
                    security_plugin='noop_auth_backend')
    server.connect(endpoint)
    server.stop()


def make_one_client_socket(endpoint):
    context = zmq.Context.instance()
    req_sock = context.socket(zmq.ROUTER)
    req_sock.connect(endpoint)
    return req_sock


def make_one_server(user_id, endpoint):
    from pseud._gevent import Server
    server = Server(user_id)
    server.bind(endpoint)
    return server


def test_job_running():
    from pseud.common import msgpack_packb
    from pseud.interfaces import EMPTY_DELIMITER, OK, VERSION, WORK
    from pseud.utils import register_rpc

    @register_rpc
    def job_success(a, b, c, d=None):
        time.sleep(.2)
        return True

    user_id = b'echo'
    endpoint = 'inproc://{}'.format(__name__).encode()
    server = make_one_server(user_id, endpoint)
    server.start()
    socket = make_one_client_socket(endpoint)
    work = msgpack_packb(('job_success', (1, 2, 3), {'d': False}))
    gevent.spawn(socket.send_multipart, [user_id, EMPTY_DELIMITER, VERSION,
                                         EMPTY_DELIMITER, WORK, work])
    response = gevent.spawn(read_once, socket).get()
    assert response == [user_id, EMPTY_DELIMITER, VERSION, EMPTY_DELIMITER,
                        OK, msgpack_packb(True)]
    server.stop()


def test_job_not_found():
    from pseud.common import msgpack_packb, msgpack_unpackb
    import pseud
    from pseud.interfaces import EMPTY_DELIMITER, ERROR, VERSION, WORK
    user_id = b'echo'
    endpoint = 'inproc://{}'.format(__name__).encode()
    server = make_one_server(user_id, endpoint)
    socket = make_one_client_socket(endpoint)
    work = msgpack_packb(('thisIsNotAFunction', (), {}))
    server.start()
    gevent.spawn(socket.send_multipart, [user_id, EMPTY_DELIMITER, VERSION,
                                         EMPTY_DELIMITER, WORK, work])
    result = gevent.event.AsyncResult()
    gevent.spawn(read_once, socket).link(result)
    response = result.get()
    assert response[:-1] == [user_id, EMPTY_DELIMITER, VERSION,
                             EMPTY_DELIMITER, ERROR]
    klass, message, traceback = msgpack_unpackb(response[-1])
    assert klass == 'ServiceNotFoundError'
    assert message == 'thisIsNotAFunction'
    # pseud.__file__ might ends with .pyc
    assert os.path.dirname(pseud.__file__) in traceback
    server.stop()


def test_job_raise():
    from pseud.common import msgpack_packb, msgpack_unpackb
    from pseud.interfaces import EMPTY_DELIMITER, ERROR, VERSION, WORK
    from pseud.utils import register_rpc

    @register_rpc
    def job_buggy(*args, **kw):
        raise ValueError('too bad')

    user_id = b'echo'
    endpoint = 'inproc://{}'.format(__name__).encode()
    server = make_one_server(user_id, endpoint)
    socket = make_one_client_socket(endpoint)
    work = msgpack_packb(('job_buggy', (), {}))
    server.start()
    gevent.spawn(socket.send_multipart, [user_id, EMPTY_DELIMITER, VERSION,
                                         EMPTY_DELIMITER, WORK, work])
    result = gevent.event.AsyncResult()
    gevent.spawn(read_once, socket).link(result)
    response = result.get()
    assert response[:-1] == [user_id, b'', VERSION, b'', ERROR]
    klass, message, traceback = msgpack_unpackb(response[-1])
    assert klass == 'ValueError'
    assert message == 'too bad'
    assert __file__ in traceback
    server.stop()
