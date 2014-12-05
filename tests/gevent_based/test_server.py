import os.path
import time

import pytest
gevent = pytest.importorskip('gevent')
import zmq.green as zmq


def read_once(socket):
    return socket.recv_multipart()


def test_server_creation():
    from pseud._gevent import Server
    user_id = 'echo'
    server = Server(user_id)
    assert server.user_id == user_id
    assert server.security_plugin == 'noop_auth_backend'


def test_server_can_bind():
    from pseud._gevent import Server
    user_id = 'echo'
    endpoint = 'inproc://{}'.format(__name__)
    server = Server(user_id,
                    security_plugin='noop_auth_backend')
    server.bind(endpoint)
    server.stop()


def test_server_can_connect():
    from pseud._gevent import Server
    user_id = 'echo'
    endpoint = 'tcp://127.0.0.1:5000'
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
    from pseud.interfaces import OK, VERSION, WORK
    from pseud.utils import register_rpc
    from pseud.packer import Packer

    @register_rpc
    def job_success(a, b, c, d=None):
        time.sleep(.2)
        return True

    user_id = 'echo'
    endpoint = 'inproc://{}'.format(__name__)
    server = make_one_server(user_id, endpoint)
    server.start()
    socket = make_one_client_socket(endpoint)
    work = Packer().packb((job_success.func_name, (1, 2, 3), {'d': False}))
    gevent.spawn(socket.send_multipart, [user_id, '', VERSION,
                                         '', WORK, work])
    response = gevent.spawn(read_once, socket).get()
    assert response == [user_id, '', VERSION, '', OK, Packer().packb(True)]
    server.stop()


def test_job_not_found():
    from pseud.packer import Packer
    import pseud
    from pseud.interfaces import ERROR, VERSION, WORK
    user_id = 'echo'
    endpoint = 'inproc://{}'.format(__name__)
    server = make_one_server(user_id, endpoint)
    socket = make_one_client_socket(endpoint)
    work = Packer().packb(('thisIsNotAFunction', (), {}))
    server.start()
    gevent.spawn(socket.send_multipart, [user_id, '', VERSION,
                                         '', WORK, work])
    result = gevent.event.AsyncResult()
    gevent.spawn(read_once, socket).link(result)
    response = result.get()
    assert response[:-1] == [user_id, '', VERSION, '', ERROR]
    klass, message, traceback = Packer().unpackb(response[-1])
    assert klass == 'ServiceNotFoundError'
    assert message == 'thisIsNotAFunction'
    # pseud.__file__ might ends with .pyc
    assert os.path.dirname(pseud.__file__) in traceback
    server.stop()


def test_job_raise():
    from pseud.interfaces import ERROR, VERSION, WORK
    from pseud.packer import Packer
    from pseud.utils import register_rpc

    @register_rpc
    def job_buggy(*args, **kw):
        raise ValueError('too bad')

    user_id = 'echo'
    endpoint = 'inproc://{}'.format(__name__)
    server = make_one_server(user_id, endpoint)
    socket = make_one_client_socket(endpoint)
    work = Packer().packb((job_buggy.func_name, (), {}))
    server.start()
    gevent.spawn(socket.send_multipart, [user_id, '', VERSION,
                                         '', WORK, work])
    result = gevent.event.AsyncResult()
    gevent.spawn(read_once, socket).link(result)
    response = result.get()
    assert response[:-1] == [user_id, '', VERSION, '', ERROR]
    klass, message, traceback = Packer().unpackb(response[-1])
    assert klass == 'ValueError'
    assert message == 'too bad'
    assert __file__ in traceback
    server.stop()
