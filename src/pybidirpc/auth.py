import itertools

import zope.component
import zope.interface
import zmq

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
        self.rpc.socket.curve_secretkey = self.rpc.private_key
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
        self.rpc.socket.curve_secretkey = self.rpc.private_key
        self.rpc.socket.curve_server = True
        assert self.rpc.socket.mechanism == zmq.CURVE
        assert self.rpc.socket.get(zmq.CURVE_SERVER)
        self.zap_socket = zap_socket = self.rpc.context.socket(zmq.REP)
        zap_socket.linger = 1
        zap_socket.bind('inproc://zeromq.zap.01')
        self.rpc.read_forever(zap_socket,
                              self._zap_handler)

    def _zap_handler(self, message):
        """
        http://rfc.zeromq.org/spec:27
        """
        version, sequence, domain, address, identity, mechanism, key =\
            message
        assert version == '1.0'
        assert mechanism == 'CURVE'
        reply = [version, sequence, '200', 'OK', self.name, '']
        self.zap_socket.send_multipart(reply)

    def handle_hello(self, *args):
        pass

    def handle_authenticated(self, message):
        pass

    def save_last_work(self, message):
        pass

    def is_authenticated(self, peer_id):
        return True

    def stop(self):
        self.zap_socket.close()


@register_auth_backend
@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IClient)
class CurveWithUntrustedKeyForClient(_BaseAuthBackend):
    """
    Server doesn't trust peer certificate.
    Requires to do 2 step authentication.
    1. CURVE + PLAIN, then approve key if authenticated.
    2. CURVE (trusted version)
    """
    name = 'untrusted_curve'
    last_message = None
    counter = itertools.count()

    def configure(self):
        self.rpc.socket.curve_serverkey = self.rpc.peer_public_key
        self.rpc.socket.curve_publickey = self.rpc.public_key
        self.rpc.socket.curve_secretkey = self.rpc.private_key
        assert self.rpc.socket.mechanism == zmq.CURVE

    def handle_authentication(self, peer_id, message_uuid):
        if next(self.counter) >= 3:
            future = self.rpc.future_pool[message_uuid]
            future.set_exception(UnauthorizedError('Max authentication'
                                                   ' retries reached'))
        else:
            self.rpc.send_message([peer_id, VERSION, message_uuid,
                                   HELLO, self.rpc.password])

    def handle_hello(self, *args):
        pass

    def handle_authenticated(self, message_uuid):
        self.rpc.send_message(self.last_message)
        self.last_message = None

    def save_last_work(self, message):
        self.last_message = message

    def is_authenticated(self, peer_id):
        return True

    def stop(self):
        pass


@register_auth_backend
@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IServer)
class CurveWithUntrustedKeyForServer(_BaseAuthBackend):
    """
    Server doesn't trust peer certificate.
    Requires to do 2 step authentication.
    1. CURVE + PLAIN
    2. CURVE (trusted version)

    note..

        This implementation should not be used on production.
        It is just for the tests.
    """
    name = 'untrusted_curve'

    trusted_keys = {}
    pending_keys = {}
    user_map = {}
    current_untrusted_key = None

    def _zap_handler(self, message):
        """
        http://rfc.zeromq.org/spec:27
        """
        version, sequence, domain, address, identity, mechanism, key =\
            message
        assert version == '1.0'
        assert mechanism == 'CURVE'
        if key not in self.trusted_keys:
            self.current_untrusted_key = key
        reply = [version, sequence, '200', 'OK', self.name, '']
        self.zap_socket.send_multipart(reply)

    def configure(self):
        self.rpc.socket.curve_publickey = self.rpc.public_key
        self.rpc.socket.curve_secretkey = self.rpc.private_key
        self.rpc.socket.curve_server = True
        assert self.rpc.socket.mechanism == zmq.CURVE
        assert self.rpc.socket.get(zmq.CURVE_SERVER)
        self.zap_socket = zap_socket = self.rpc.context.socket(zmq.REP)
        zap_socket.linger = 1
        zap_socket.bind('inproc://zeromq.zap.01')
        self.reader = self.rpc.read_forever(zap_socket,
                                            self._zap_handler)

    def handle_hello(self, peer_id, message_uuid, message):
        if peer_id in self.user_map and self.user_map[peer_id] == message:
            self.trusted_keys[self.pending_keys.pop(peer_id)] = peer_id
            reply = 'Welcome {}'.format(peer_id)
            status = AUTHENTICATED
        else:
            reply = 'Authentication Error'
            status = UNAUTHORIZED
        print 'Sending Hello reply', reply
        self.rpc.send_message([peer_id, VERSION, message_uuid,
                               status, reply])

    def handle_authenticated(self, message):
        pass

    def handle_authentication(self, peer_id, message_uuid):
        if self.current_untrusted_key is not None:
            self.pending_keys[peer_id] = self.current_untrusted_key
            self.current_untrusted_key = None
        reply = 'Authentication Error'
        status = UNAUTHORIZED
        self.rpc.send_message([peer_id, VERSION, message_uuid,
                               status, reply])

    def is_authenticated(self, peer_id):
        return (self.current_untrusted_key is None
                and (peer_id not in self.pending_keys
                     or peer_id in self.trusted_keys.values()))

    def stop(self):
        try:
            self.reader.kill()
        except AttributeError:
            pass

        self.zap_socket.close()

    def save_last_work(self, message):
        pass