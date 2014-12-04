from __future__ import unicode_literals
import threading
import uuid

import pytest
import zmq


def test_client_creation():
    from pseud import SyncClient
    client = SyncClient()
    assert client.security_plugin == 'noop_auth_backend'


def test_client_can_bind():
    from pseud import SyncClient
    endpoint = 'inproc://{}'.format(__name__).encode()
    client = SyncClient()
    client.bind(endpoint)
    client.stop()


def test_client_can_connect():
    from pseud import SyncClient
    endpoint = 'inproc://{}'.format(__name__).encode()
    client = SyncClient()
    client.connect(endpoint)
    client.stop()


def make_one_server_thread(context, identity, endpoint, callback):
    router_sock = context.socket(zmq.ROUTER)
    router_sock.identity = identity
    router_sock.bind(endpoint)
    response = router_sock.recv_multipart()
    callback(router_sock, response)


def make_one_client(timeout=5):
    from pseud import SyncClient
    client = SyncClient(timeout=timeout)
    return client


def test_client_method_wrapper():
    from pseud.common import AttributeWrapper
    endpoint = 'inproc://{}'.format(__name__)
    client = make_one_client()
    method_name = 'a.b.c.d'
    with pytest.raises(RuntimeError):
        # If not connected can not call anything
        wrapper = getattr(client, method_name)
    client.connect(endpoint)
    wrapper = getattr(client, method_name)
    assert isinstance(wrapper, AttributeWrapper)
    assert wrapper._part_names == method_name.split('.')
    assert wrapper.name == method_name
    # with pytest.raises(TimeoutError):
    #     wrapper()
    client.stop()


def test_job_executed():
    from pseud.interfaces import OK, VERSION, WORK
    from pseud.packer import Packer
    context = zmq.Context.instance()
    endpoint = 'ipc://{}'.format(__name__)
    peer_identity = b'server'

    def server_callback(socket, request):
        peer_id, _, version, uid, message_type, message = request
        assert _ == b''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = Packer().unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == [1, 2, 3]
        assert kw == {'b': 4}
        reply = [peer_id, _, version, uid, OK, Packer().packb(True)]
        socket.send_multipart(reply)

    thread = threading.Thread(target=make_one_server_thread,
                              args=(context, peer_identity, endpoint,
                                    server_callback))
    thread.start()
    client = make_one_client()
    client.connect(endpoint)

    result = client.please.do_that_job(1, 2, 3, b=4)
    assert result is True
    client.stop()
    thread.join()


def test_job_failure():
    from pseud.interfaces import ERROR, VERSION, WORK
    from pseud.packer import Packer
    context = zmq.Context.instance()
    endpoint = 'ipc://{}'.format(__name__)
    peer_identity = b'server'

    def server_callback(socket, request):
        peer_id, _, version, uid, message_type, message = request
        assert _ == b''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = Packer().unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == [1, 2, 3]
        assert kw == {'b': 4}
        reply = [peer_id, _, version, uid, ERROR, Packer().packb(
            ('ValueError', 'too bad', 'traceback'))]
        socket.send_multipart(reply)

    thread = threading.Thread(target=make_one_server_thread,
                              args=(context, peer_identity, endpoint,
                                    server_callback))
    thread.start()
    client = make_one_client()
    client.connect(endpoint)

    with pytest.raises(ValueError):
        client.please.do_that_job(1, 2, 3, b=4)
    client.stop()
    thread.join()


def test_job_failure_service_not_found():
    from pseud.interfaces import ERROR, VERSION, WORK, ServiceNotFoundError
    from pseud.packer import Packer
    context = zmq.Context.instance()
    endpoint = 'ipc://{}'.format(__name__)
    peer_identity = b'server'

    def server_callback(socket, request):
        peer_id, _, version, uid, message_type, message = request
        assert _ == b''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = Packer().unpackb(message)
        assert locator == 'please.do_that_job'
        assert args == [1, 2, 3]
        assert kw == {'b': 4}
        reply = [peer_id, _, version, uid, ERROR, Packer().packb(
            ('ServiceNotFoundError', 'too bad', 'traceback'))]
        socket.send_multipart(reply)

    thread = threading.Thread(target=make_one_server_thread,
                              args=(context, peer_identity, endpoint,
                                    server_callback))
    thread.start()
    client = make_one_client()
    client.connect(endpoint)

    with pytest.raises(ServiceNotFoundError):
        client.please.do_that_job(1, 2, 3, b=4)
    client.stop()
    thread.join()


def test_job_server_never_reply():
    from pseud.interfaces import TimeoutError, VERSION, WORK
    from pseud.packer import Packer
    context = zmq.Context.instance()
    endpoint = 'ipc://{}'.format(__name__)
    peer_identity = b'server'

    def server_callback(socket, request):
        peer_id, _, version, uid, message_type, message = request
        assert _ == ''
        assert version == VERSION
        assert uid
        # check it is a real uuid
        uuid.UUID(bytes=uid)
        assert message_type == WORK
        locator, args, kw = Packer().unpackb(message)
        assert locator == b'please.do_that_job'
        assert args == [1, 2]
        assert kw == {'b': 5}

    thread = threading.Thread(target=make_one_server_thread,
                              args=(context, peer_identity, endpoint,
                                    server_callback))
    thread.start()
    client = make_one_client(timeout=.2)
    client.connect(endpoint)

    with pytest.raises(TimeoutError):
        client.please.do_that_job(1, 2, b=5)
    client.stop()
    thread.join()
