import zope.interface


AUTHENTICATED = '\x04'
OK = '\x01'
HELLO = '\x02'
WORK = '\x03'
ERROR = '\x10'
UNAUTHORIZED = '\x11'

VERSION = 'v1'


class TimeoutError(Exception):
    pass


class ServiceNotFoundError(Exception):
    pass


class UnauthorizedError(Exception):
    pass


class IAuthenticationBackend(zope.interface.Interface):

    def configure():
        """
        Hook to adapt your RPC peer.
        Must be used to start any service like a zap_handler
        """

    def stop():
        """
        Hook to stop any service running in background.
        Can be either IOLoop, threading, or multiprocess.
        """

    def handle_hello(message, peer_id, message_uuid):
        """
        """

    def handle_authenticated(message):
        """
        """

    def save_last_work(message):
        """
        """

    def is_authenticated(peer_id):
        """
        """


class IClient(zope.interface.Interface):
    """
    Interface for Clients
    """


class IServer(zope.interface.Interface):
    """
    Interface for Servers
    """
