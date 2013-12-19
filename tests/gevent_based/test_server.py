import os.path
import time

import gevent
import msgpack
import zmq.green as zmq


def read_once(socket):
    return socket.recv_multipart()


def test_server_creation():
    from pybidirpc._gevent import Server
    import pybidirpc.auth, pybidirpc.heartbeat  # NOQA
    identity = 'echo'
    server = Server(identity)
    assert server.identity == identity
    assert server.security_plugin == 'noop_auth_backend'


def test_server_can_bind():
    from pybidirpc._gevent import Server
    import pybidirpc.auth, pybidirpc.heartbeat  # NOQA
    identity = 'echo'
    endpoint = 'inproc://{}'.format(__name__)
    server = Server(identity,
                    security_plugin='noop_auth_backend')
    server.bind(endpoint)
    server.stop()


def test_server_can_connect():
    from pybidirpc._gevent import Server
    import pybidirpc.auth, pybidirpc.heartbeat  # NOQA
    identity = 'echo'
    endpoint = 'tcp://127.0.0.1:5000'
    server = Server(identity,
                    security_plugin='noop_auth_backend')
    server.connect(endpoint)
    server.stop()


def make_one_client_socket(identity, endpoint):
    context = zmq.Context.instance()
    req_sock = context.socket(zmq.ROUTER)
    req_sock.identity = identity
    req_sock.connect(endpoint)
    return req_sock


def make_one_server(identity, endpoint):
    from pybidirpc._gevent import Server
    import pybidirpc.auth, pybidirpc.heartbeat  # NOQA
    import pybidirpc.predicate  # NOQA
    server = Server(identity)
    server.bind(endpoint)
    return server


def test_job_running():
    from pybidirpc.interfaces import OK, VERSION, WORK
    from pybidirpc.utils import register_rpc

    @register_rpc
    def job_success(a, b, c, d=None):
        time.sleep(.2)
        return True

    identity = 'echo'
    endpoint = 'inproc://{}'.format(__name__)
    server = make_one_server(identity, endpoint)
    server.start()
    socket = make_one_client_socket('client', endpoint)
    work = msgpack.packb((job_success.func_name, (1, 2, 3), {'d': False}))
    gevent.spawn(socket.send_multipart, [identity, VERSION, '', WORK, work])
    response = gevent.spawn(read_once, socket).get()
    assert response == [identity, VERSION, '', OK, msgpack.packb(True)]
    server.stop()


def test_job_not_found():
    import pybidirpc
    from pybidirpc.interfaces import ERROR, VERSION, WORK
    identity = 'echo'
    endpoint = 'inproc://{}'.format(__name__)
    server = make_one_server(identity, endpoint)
    socket = make_one_client_socket('client', endpoint)
    work = msgpack.packb(('thisIsNotAFunction', (), {}))
    server.start()
    gevent.spawn(socket.send_multipart, [identity, VERSION, '', WORK, work])
    result = gevent.event.AsyncResult()
    gevent.spawn(read_once, socket).link(result)
    response = result.get()
    assert response[:-1] == [identity, VERSION, '', ERROR]
    klass, message, traceback = msgpack.unpackb(response[-1])
    assert klass == 'ServiceNotFoundError'
    assert message == 'thisIsNotAFunction'
    # pybidirpc.__file__ might ends with .pyc
    assert os.path.dirname(pybidirpc.__file__) in traceback
    server.stop()


def test_job_raise():
    from pybidirpc.interfaces import ERROR, VERSION, WORK
    from pybidirpc.utils import register_rpc

    @register_rpc
    def job_buggy(*args, **kw):
        raise ValueError('too bad')

    identity = 'echo'
    endpoint = 'inproc://{}'.format(__name__)
    server = make_one_server(identity, endpoint)
    socket = make_one_client_socket('client', endpoint)
    work = msgpack.packb((job_buggy.func_name, (), {}))
    server.start()
    gevent.spawn(socket.send_multipart, [identity, VERSION, '', WORK, work])
    result = gevent.event.AsyncResult()
    gevent.spawn(read_once, socket).link(result)
    response = result.get()
    assert response[:-1] == [identity, VERSION, '', ERROR]
    klass, message, traceback = msgpack.unpackb(response[-1])
    assert klass == 'ValueError'
    assert message == 'too bad'
    assert __file__ in traceback
    server.stop()
