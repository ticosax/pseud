import itertools
import logging

import zope.component
import zope.interface
import zmq

from .common import msgpack_packb, msgpack_unpackb
from .interfaces import (AUTHENTICATED,
                         IAuthenticationBackend,
                         IClient,
                         IServer,
                         HELLO,
                         UNAUTHORIZED,
                         UnauthorizedError,
                         VERSION,
                         )
from .utils import register_auth_backend

logger = logging.getLogger(__name__)


class _BaseAuthBackend(object):

    def __init__(self, rpc):
        self.rpc = rpc


@register_auth_backend
@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IClient)
class NoOpAuthenticationBackendForClient(_BaseAuthBackend):
    """
    Just allow anything
    """
    name = 'noop_auth_backend'

    def stop(self):
        pass

    def configure(self):
        pass

    def handle_hello(self, *args):
        pass

    def handle_authenticated(self, message):
        pass

    def is_authenticated(self, peer_id):
        return True

    def save_last_work(self, message):
        pass

    def get_predicate_arguments(self, peer_id):
        return {}

    def get_destination_id(self, identity):
        return identity


@register_auth_backend
@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IServer)
class NoOpAuthenticationBackendForServer(NoOpAuthenticationBackendForClient):
    pass


@register_auth_backend
@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IClient)
class CurveWithTrustedKeyForClient(_BaseAuthBackend):
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

    def stop(self):
        pass

    def handle_hello(self, *args):
        pass

    def handle_authenticated(self, message):
        pass

    def save_last_work(self, message):
        pass

    def is_authenticated(self, peer_id):
        return True

    def get_predicate_arguments(self, peer_id):
        return {}

    def get_destination_id(self, identity):
        return identity


@register_auth_backend
@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IServer)
class CurveWithTrustedKeyForServer(_BaseAuthBackend):
    """
    Server trusts peer certificate and allows every peer.
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
        zap_socket.bind('inproc://zeromq.zap.01')
        self.reader = self.rpc.read_forever(zap_socket,
                                            self._zap_handler)

    def _zap_handler(self, message):
        """
        `ZAP <http://rfc.zeromq.org/spec:27>`_
        """
        (zid, delimiter, version, sequence, domain, address, identity,
         mechanism, key) = message
        assert version == '1.0'
        assert mechanism == 'CURVE'
        reply = [zid, delimiter, version, sequence, '200', 'OK', self.name, '']
        self.zap_socket.send_multipart(reply)

    def handle_hello(self, *args):
        pass

    def handle_authenticated(self, message):
        pass

    def save_last_work(self, message):
        pass

    def is_authenticated(self, peer_id):
        return True

    def get_predicate_arguments(self, peer_id):
        return {}

    def get_destination_id(self, identity):
        return identity

    def stop(self):
        try:
            self.reader.kill()
        except AttributeError:
            self.reader.on_recv(None)
            self.reader.flush()
            self.reader.close()
        self.zap_socket.close()
        self.zap_socket = None


@register_auth_backend
@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IClient)
class CurveWithUntrustedKeyForClient(_BaseAuthBackend):
    """
    Server doesn't trust peer certificate.
    Requires to do 2 step authentication.

    #. CURVE + PLAIN, then approve key if authenticated.
    #. CURVE (trusted version)
    """
    name = 'untrusted_curve'
    max_retries = 2

    def __init__(self, *args, **kw):
        super(CurveWithUntrustedKeyForClient, self).__init__(*args, **kw)
        self.counter = itertools.count()
        self.last_messages = []

    def configure(self):
        self.rpc.socket.curve_serverkey = self.rpc.peer_public_key
        self.rpc.socket.curve_publickey = self.rpc.public_key
        self.rpc.socket.curve_secretkey = self.rpc.secret_key
        assert self.rpc.socket.mechanism == zmq.CURVE

    def handle_authentication(self, peer_id, message_uuid):
        if next(self.counter) >= self.max_retries:
            try:
                future = self.rpc.future_pool.pop(message_uuid)
            except KeyError:
                pass
            else:
                future.set_exception(UnauthorizedError('Max authentication'
                                                       ' retries reached'))
        else:
            self.rpc.send_message([peer_id, '', VERSION, message_uuid,
                                   HELLO,
                                   msgpack_packb((self.rpc.login,
                                                  self.rpc.password))])

    def handle_hello(self, *args):
        pass

    def handle_authenticated(self, message_uuid):
        try:
            self.rpc.send_message(self.last_messages.pop(0))
        except IndexError:
            pass
        self.last_message = None

    def save_last_work(self, message):
        self.last_messages.append(message)

    def is_authenticated(self, peer_id):
        return True

    def stop(self):
        pass

    def get_predicate_arguments(self, peer_id):
        return {}

    def get_destination_id(self, identity):
        return identity


def find_key_from_value(mapping, value):
    for key, _value in mapping.iteritems():
        if _value == value:
            yield key


@register_auth_backend
@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IServer)
class CurveWithUntrustedKeyForServer(_BaseAuthBackend):
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
        self.current_untrusted_key = None
        self.connection_renewed = None

    def _zap_handler(self, message):
        """
        http://rfc.zeromq.org/spec:27
        """
        (zid, delimiter, version, sequence, domain, address, identity,
         mechanism, key) = message
        assert version == '1.0'
        assert mechanism == 'CURVE'
        if key not in self.trusted_keys:
            self.current_untrusted_key = key
        else:
            self.connection_renewed = key
        reply = [zid, delimiter, version, sequence, '200', 'OK', self.name, '']
        self.zap_socket.send_multipart(reply)

    def configure(self):
        self.rpc.socket.curve_publickey = self.rpc.public_key
        self.rpc.socket.curve_secretkey = self.rpc.secret_key
        self.rpc.socket.curve_server = True
        assert self.rpc.socket.mechanism == zmq.CURVE
        assert self.rpc.socket.get(zmq.CURVE_SERVER)
        self.zap_socket = zap_socket = self.rpc.context.socket(zmq.ROUTER)
        zap_socket.linger = 1
        zap_socket.bind('inproc://zeromq.zap.01')
        self.reader = self.rpc.read_forever(zap_socket,
                                            self._zap_handler)

    def get_destination_id(self, identity):
        return self.login2peer_id_mapping[identity]

    def handle_hello(self, peer_id, message_uuid, message):
        login, password = msgpack_unpackb(message)
        if login in self.user_map and self.user_map[login] == password:
            key = self.pending_keys[peer_id]
            self.trusted_keys[key] = peer_id
            self.login2peer_id_mapping[login] = peer_id
            reply = 'Welcome {}'.format(peer_id)
            status = AUTHENTICATED
        else:
            reply = 'Authentication Error'
            status = UNAUTHORIZED
        logger.debug('Sending Hello reply: {!r}'.format(reply))
        self.rpc.send_message([peer_id, '', VERSION, message_uuid,
                               status, reply])

    def handle_authenticated(self, message):
        pass

    def handle_authentication(self, peer_id, message_uuid):
        if self.current_untrusted_key is not None:
            self.pending_keys[peer_id] = self.current_untrusted_key
            self.current_untrusted_key = None
        reply = 'Authentication Required'
        status = UNAUTHORIZED
        self.rpc.send_message([peer_id, '', VERSION, message_uuid,
                               status, reply])

    def is_authenticated(self, peer_id):
        if (self.current_untrusted_key is None
            and (peer_id not in self.pending_keys
                 or peer_id in self.trusted_keys.values())):
            try:
                self.pending_keys[peer_id]
            except KeyError:
                pass
            if self.connection_renewed:
                # We know that a trusted key just reconnect
                # updates mappings where socket_id is used
                previous_peer_id = self.trusted_keys[self.connection_renewed]
                iterator = find_key_from_value(self.login2peer_id_mapping,
                                               previous_peer_id)
                login = next(iterator)
                try:
                    next(iterator)
                except StopIteration:
                    pass
                else:
                    del self.trusted_keys[self.connection_renewed]
                    del self.login2peer_id_mapping[login]
                    self.connection_renewed = None
                    raise RuntimeError('Two peer with same identity has been'
                                       ' detected')

                self.login2peer_id_mapping[login] = peer_id
                self.trusted_keys[self.connection_renewed] = peer_id
                self.connection_renewed = None
            return True
        return False

    def stop(self):
        try:
            self.reader.kill()
        except AttributeError:
            self.reader.on_recv(None)
            self.reader.flush()
            self.reader.close()
        self.zap_socket.close()

    def save_last_work(self, message):
        pass

    def get_predicate_arguments(self, peer_id):
        return {}
