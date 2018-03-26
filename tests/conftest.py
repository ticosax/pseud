import asyncio
import contextlib
import itertools
import logging

import pytest
import zope.component
import zope.interface
import zmq
import zmq.asyncio
from zmq.utils import z85

import pseud
from pseud.common import handle_result, read_forever
from pseud.interfaces import (
    AUTHENTICATED,
    EMPTY_DELIMITER,
    IAuthenticationBackend,
    IClient,
    IHeartbeatBackend,
    IServer,
    HEARTBEAT,
    HELLO,
    VERSION,
    UnauthorizedError,
    UNAUTHORIZED,
)
from pseud.packer import Packer
from pseud.utils import register_auth_backend, register_heartbeat_backend

logger = logging.getLogger(pseud.__name__)


@zope.interface.implementer(IHeartbeatBackend)
@zope.component.adapter(IClient)
class TestingHeartbeatBackendForClient:
    name = 'testing_heartbeat_backend'

    def __init__(self, rpc):
        self.rpc = rpc

    async def handle_timeout(self, user_id, routing_id):
        pass

    async def handle_heartbeat(self, user_id, routing_id):
        while True:
            await asyncio.shield(self.rpc.send_message(
                [routing_id, b'', VERSION, b'', HEARTBEAT, b'']))
            await asyncio.sleep(.1)

    def configure(self):
        self.task = self.rpc.loop.create_task(
            self.handle_heartbeat(b'', self.rpc.peer_routing_id))
        self.task.add_done_callback(handle_result)

    async def stop(self):
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task


@zope.interface.implementer(IHeartbeatBackend)
@zope.component.adapter(IServer)
class TestingHeartbeatBackendForServer:
    name = 'testing_heartbeat_backend'
    timeout = .2
    task_pool = {}

    def __init__(self, rpc):
        self.rpc = rpc

    async def handle_timeout(self, user_id, routing_id):
        await asyncio.sleep(self.timeout)
        logger.debug(f'Timeout detected for {routing_id}')
        user_id_str = user_id.decode('utf-8')
        await self.monitoring_socket.send(f'Gone {user_id_str}'.encode())

    async def handle_heartbeat(self, user_id, routing_id):
        await self.monitoring_socket.send(user_id)
        try:
            task = self.task_pool[user_id]
        except KeyError:
            pass
        else:
            task.cancel()

        self.task_pool[user_id] = self.rpc.loop.create_task(
            self.handle_timeout(user_id, routing_id))

    def configure(self):
        self.monitoring_socket = self.rpc.context.socket(zmq.PUB)
        self.monitoring_socket.bind(b'ipc://testing_heartbeating_backend')

    async def stop(self):
        self.monitoring_socket.close(linger=0)
        for task in self.task_pool.values():
            task.cancel()


@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IClient)
class PlainForClient:
    """
    Simple username password auth
    """
    name = 'plain'

    def __init__(self, rpc):
        self.rpc = rpc

    def configure(self):
        self.rpc.socket.plain_username = self.rpc.user_id
        self.rpc.socket.plain_password = self.rpc.password
        assert self.rpc.socket.mechanism == zmq.PLAIN

    async def stop(self):
        pass

    async def handle_hello(self, *args):
        pass

    async def handle_authenticated(self, message):
        pass

    def save_last_work(self, message):
        pass

    def is_authenticated(self, peer_id):
        return True

    def get_predicate_arguments(self, peer_id):
        return {}

    def get_routing_id(self, user_id):
        return user_id

    def register_routing_id(self, user_id, routing_id):
        pass


@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IServer)
class PlainForServer:
    """
    Allow peers to connect if username == password
    using PLAIN mechanism.

    .. note::
        For testing usage only
    """
    name = 'plain'

    def __init__(self, rpc):
        self.rpc = rpc
        self.routing_mapping = {}

    def configure(self):
        self.rpc.socket.plain_server = True
        assert self.rpc.socket.mechanism == zmq.PLAIN
        assert self.rpc.socket.get(zmq.PLAIN_SERVER)
        self.zap_socket = zap_socket = self.rpc.context.socket(zmq.ROUTER)
        zap_socket.linger = 1
        zap_socket.bind('inproc://zeromq.zap.01')
        self.reader = self.rpc.loop.create_task(
            read_forever(zap_socket, self._zap_handler, copy=True))

    async def _zap_handler(self, message):
        """
        `ZAP <http://rfc.zeromq.org/spec:27>`_
        """
        (zid, delimiter, version, sequence, domain, address, identity,
         mechanism, login, password) = message
        assert version == b'1.0'
        assert mechanism == b'PLAIN'
        if login == password:
            response_code = b'200'
            response_msg = b'OK'
            known_identity = login
        else:
            known_identity = b''
            response_code = b'400'
            response_msg = b'Unauthorized'

        reply = [zid, delimiter, version, sequence, response_code,
                 response_msg, known_identity, b'']
        await self.zap_socket.send_multipart(reply)

    async def handle_hello(self, *args):
        pass

    async def handle_authenticated(self, message):
        pass

    def save_last_work(self, message):
        pass

    def is_authenticated(self, peer_id):
        return True

    def get_predicate_arguments(self, peer_id):
        return {}

    def get_routing_id(self, user_id):
        return self.routing_mapping[user_id]

    def register_routing_id(self, user_id, routing_id):
        self.routing_mapping[user_id] = routing_id

    async def stop(self):
        self.reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.reader
        self.zap_socket.close()
        self.zap_socket = None


@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IServer)
class TrustedPeerForServer(PlainForServer):
    """
    Trust id given by remote peer, using PLAIN mechanism.
    There is no password control.
    """
    name = 'trusted_peer'

    def _zap_handler(self, message):
        """
        `ZAP <http://rfc.zeromq.org/spec:27>`_
        """
        (zid, delimiter, version, sequence, domain, address, identity,
         mechanism, login, password) = message
        assert version == b'1.0'
        assert mechanism == b'PLAIN'
        response_code = b'200'
        response_msg = b'OK'
        known_identity = login

        reply = [zid, delimiter, version, sequence, response_code,
                 response_msg, known_identity, b'']
        self.zap_socket.send_multipart(reply)


@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IClient)
class CurveWithTrustedKeyForClient:
    """
    Server trusts peer certificate and allows every peer.
    """
    name = 'trusted_curve'

    def __init__(self, rpc):
        self.rpc = rpc

    def configure(self):
        self.rpc.socket.curve_serverkey = self.rpc.peer_public_key
        self.rpc.socket.curve_publickey = self.rpc.public_key
        self.rpc.socket.curve_secretkey = self.rpc.secret_key
        assert self.rpc.socket.mechanism == zmq.CURVE

    async def stop(self):
        pass

    async def handle_hello(self, *args):
        pass

    async def handle_authenticated(self, message):
        pass

    def save_last_work(self, message):
        pass

    def is_authenticated(self, peer_id):
        return True

    def get_predicate_arguments(self, peer_id):
        return {}

    def get_routing_id(self, user_id):
        return user_id

    def register_routing_id(self, user_id, routing_id):
        pass


@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IServer)
class CurveWithTrustedKeyForServer:
    """
    Server trusts peer certificate and allows every peer.

    Note: This is an example for testing only.
    """
    name = 'trusted_curve'

    def __init__(self, rpc):
        self.rpc = rpc

    def configure(self):
        self.rpc.socket.curve_publickey = self.rpc.public_key
        self.rpc.socket.curve_secretkey = self.rpc.secret_key
        self.rpc.socket.curve_server = True
        assert self.rpc.socket.mechanism == zmq.CURVE
        assert self.rpc.socket.get(zmq.CURVE_SERVER)
        self.zap_socket = zap_socket = self.rpc.context.socket(zmq.ROUTER)
        zap_socket.linger = 1
        zap_socket.bind(b'inproc://zeromq.zap.01')
        self.reader = self.rpc.loop.create_task(
            read_forever(zap_socket, self._zap_handler, copy=True))
        self.known_identities = {b'bob': zmq.curve_keypair(),
                                 b'alice': zmq.curve_keypair()}

    async def _zap_handler(self, message):
        """
        `ZAP <http://rfc.zeromq.org/spec:27>`_
        """
        (zid, delimiter, version, sequence, domain, address, identity,
         mechanism, key) = message
        assert version == b'1.0'
        assert mechanism == b'CURVE'
        for known_identity, pair in self.known_identities.items():
            if key == z85.decode(pair[0]):
                response_code = b'200'
                response_msg = b'OK'
                break
        else:
            known_identity = b''
            response_code = b'400'
            response_msg = b'Unauthorized'

        reply = [zid, delimiter, version, sequence, response_code,
                 response_msg, known_identity, b'']
        await self.zap_socket.send_multipart(reply)

    async def handle_hello(self, *args):
        pass

    async def handle_authenticated(self, message):
        pass

    def save_last_work(self, message):
        pass

    def is_authenticated(self, peer_id):
        return True

    def get_predicate_arguments(self, peer_id):
        return {}

    def get_routing_id(self, user_id):
        return user_id

    def register_routing_id(self, user_id, routing_id):
        pass

    async def stop(self):
        self.reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.reader
        self.zap_socket.close()
        self.zap_socket = None


@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IClient)
class CurveWithUntrustedKeyForClient:
    """
    Server doesn't trust peer certificate.
    Requires to do 2 step authentication.

    #. CURVE + PLAIN, then approve key if authenticated.
    #. CURVE (trusted version)
    """
    name = 'untrusted_curve'
    max_retries = 2

    def __init__(self, rpc):
        self.rpc = rpc
        self.counter = itertools.count()
        self.last_messages = []
        self.packer = Packer()

    def configure(self):
        self.rpc.socket.curve_serverkey = self.rpc.peer_public_key
        self.rpc.socket.curve_publickey = self.rpc.public_key
        self.rpc.socket.curve_secretkey = self.rpc.secret_key
        assert self.rpc.socket.mechanism == zmq.CURVE

    async def handle_authentication(self, user_id, routing_id, message_uuid):
        if next(self.counter) >= self.max_retries:
            try:
                future = self.rpc.future_pool.pop(message_uuid)
            except KeyError:
                pass
            else:
                future.set_exception(UnauthorizedError('Max authentication'
                                                       ' retries reached'))
        else:
            await self.rpc.send_message(
                [routing_id, EMPTY_DELIMITER, VERSION,
                 message_uuid, HELLO,
                 self.packer.packb((self.rpc.user_id, self.rpc.password))])

    async def handle_hello(self, *args):
        pass

    async def handle_authenticated(self, message_uuid):
        try:
            await self.rpc.send_message(self.last_messages.pop(0))
        except IndexError:
            pass
        self.last_message = None

    def save_last_work(self, message):
        self.last_messages.append(message)

    def is_authenticated(self, peer_id):
        return True

    async def stop(self):
        pass

    def get_predicate_arguments(self, peer_id):
        return {}

    def get_routing_id(self, user_id):
        return user_id

    def register_routing_id(self, user_id, routing_id):
        pass


@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IServer)
class CurveWithUntrustedKeyForServer:
    """
    Server doesn't trust peer certificate.
    Requires to do 2 step authentication.

    #. CURVE + PLAIN
    #. CURVE (trusted version)

    .. note::

        This implementation should not be used on production.
        It is just for the tests.
    """
    name = 'untrusted_curve'

    def __init__(self, rpc):
        self.rpc = rpc
        self.trusted_keys = {}
        self.pending_keys = {}
        self.user_map = {}
        self.login2peer_id_mapping = {}
        self.packer = Packer()

    async def _zap_handler(self, message):
        """
        http://rfc.zeromq.org/spec:27
        """
        (zid, delimiter, version, sequence, domain, address, identity,
         mechanism, key) = message
        assert version == b'1.0'
        assert mechanism == b'CURVE'
        try:
            user_id = self.trusted_keys[key]
        except KeyError:
            user_id = z85.encode(key)
        reply = [zid, delimiter, version, sequence, b'200', b'OK',
                 user_id, b'']
        await self.zap_socket.send_multipart(reply)

    def configure(self):
        self.rpc.socket.curve_publickey = self.rpc.public_key
        self.rpc.socket.curve_secretkey = self.rpc.secret_key
        self.rpc.socket.curve_server = True
        assert self.rpc.socket.mechanism == zmq.CURVE
        assert self.rpc.socket.get(zmq.CURVE_SERVER)
        self.zap_socket = zap_socket = self.rpc.context.socket(zmq.ROUTER)
        zap_socket.linger = 1
        zap_socket.bind(b'inproc://zeromq.zap.01')
        self.reader = self.rpc.loop.create_task(
            read_forever(zap_socket, self._zap_handler, copy=True))

    def get_routing_id(self, user_id):
        return self.login2peer_id_mapping[user_id]

    def register_routing_id(self, user_id, routing_id):
        self.login2peer_id_mapping[user_id] = routing_id

    async def handle_hello(self, user_id, routing_id, message_uuid, message):
        login, password = self.packer.unpackb(message)
        if login in self.user_map and self.user_map[login] == password:
            key = z85.decode(self.pending_keys[routing_id])
            self.trusted_keys[key] = login
            self.login2peer_id_mapping[login] = routing_id
            try:
                del self.login2peer_id_mapping[self.pending_keys[routing_id]]
            except KeyError:
                pass
            reply = 'Welcome {!r}'.format(login).encode()
            status = AUTHENTICATED
        else:
            reply = b'Authentication Error'
            status = UNAUTHORIZED
        logger.debug('Sending Hello reply: {!r}'.format(reply))
        await self.rpc.send_message(
            [routing_id, EMPTY_DELIMITER, VERSION,
             message_uuid, status, reply])

    async def handle_authenticated(self, message):
        pass

    async def handle_authentication(self, user_id, routing_id, message_uuid):
        self.pending_keys[routing_id] = user_id  # this is the client pub key
        reply = b'Authentication Required'
        status = UNAUTHORIZED
        await self.rpc.send_message([routing_id, EMPTY_DELIMITER, VERSION,
                                     message_uuid, status, reply])

    def is_authenticated(self, user_id):
        result = False
        if user_id in self.trusted_keys:
            result = True
        try:
            if z85.decode(user_id) in self.trusted_keys:
                result = True
        except ValueError:
            pass
        if user_id in self.trusted_keys.values():
            result = True
        return result

    async def stop(self):
        self.reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.reader
        self.zap_socket.close()
        self.zap_socket = None

    def save_last_work(self, message):
        pass

    def get_predicate_arguments(self, peer_id):
        return {}


@pytest.fixture
def event_loop():
    loop = zmq.asyncio.ZMQEventLoop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def loop(event_loop):
    return event_loop


@pytest.fixture(autouse=True)
def close_context():
    yield
    context = zmq.asyncio.Context.instance()
    context.destroy(linger=0)


@pytest.fixture(scope='session')
def testing_heartbeat_backend():
    register_heartbeat_backend(TestingHeartbeatBackendForClient)
    register_heartbeat_backend(TestingHeartbeatBackendForServer)
    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      TestingHeartbeatBackendForClient)
    zope.interface.verify.verifyClass(IHeartbeatBackend,
                                      TestingHeartbeatBackendForServer)


@pytest.fixture(scope='session')
def plain_auth_backend():
    register_auth_backend(PlainForClient)
    register_auth_backend(PlainForServer)
    zope.interface.verify.verifyClass(IAuthenticationBackend, PlainForClient)
    zope.interface.verify.verifyClass(IAuthenticationBackend, PlainForServer)


@pytest.fixture(scope='session')
def trusted_peer_auth_backend():
    register_auth_backend(TrustedPeerForServer)
    zope.interface.verify.verifyClass(
        IAuthenticationBackend,
        TrustedPeerForServer)


@pytest.fixture(scope='session')
def trusted_curve_auth_backend():
    register_auth_backend(CurveWithTrustedKeyForClient)
    register_auth_backend(CurveWithTrustedKeyForServer)
    zope.interface.verify.verifyClass(
        IAuthenticationBackend,
        CurveWithTrustedKeyForClient)
    zope.interface.verify.verifyClass(
        IAuthenticationBackend,
        CurveWithTrustedKeyForServer)


@pytest.fixture(scope='session')
def untrusted_curve_auth_backend():
    register_auth_backend(CurveWithUntrustedKeyForClient)
    register_auth_backend(CurveWithUntrustedKeyForServer)
    zope.interface.verify.verifyClass(
        IAuthenticationBackend,
        CurveWithUntrustedKeyForClient)
    zope.interface.verify.verifyClass(
        IAuthenticationBackend,
        CurveWithUntrustedKeyForServer)
