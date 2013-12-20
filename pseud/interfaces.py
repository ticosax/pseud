# -*- coding: utf-8 -*-
import zope.interface


AUTHENTICATED = '\x04'
ERROR = '\x10'
HEARTBEAT = '\x06'
HELLO = '\x02'
OK = '\x01'
UNAUTHORIZED = '\x11'
WORK = '\x03'

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

registry = None  # it assume it is the globalregistry


class IBaseRPC(zope.interface.Interface):
    """
    All methods that an rpc service must support
    to handle pseud protocol
    """
    identity = zope.interface.Attribute("""
        identity of current RPC
        """)
    peer_identity = zope.interface.Attribute("""
        identity of peer to communicate with
        """)
    context = zope.interface.Attribute("""
        ØMQ context
        """)
    security_plugin = zope.interface.Attribute("""
        name of security backend to load
        """)
    initialized = zope.interface.Attribute('')
    public_key = zope.interface.Attribute('')
    secret_key = zope.interface.Attribute('')
    peer_public_key = zope.interface.Attribute('')
    password = zope.interface.Attribute('')
    heartbeat_plugin = zope.interface.Attribute('')
    heartbeat_backend = zope.interface.Attribute('')
    proxy_to = zope.interface.Attribute('')
    registry = zope.interface.Attribute('')
    io_loop = zope.interface.Attribute('')
    timeout = zope.interface.Attribute("""
        Max allowed time to send, recv or to wait for a task.
        """)

    def connect(endpoint):
        """
        Connect ØMQ socket to given endpoint
        """

    def bind(endpoint):
        """
        Bind ØMQ socket to given endpoint
        """

    def send_work(peer_identity, name, *args, **kw):
        """
        Create the ØMQ message and send it.

        Parameters
        ----------
        peer_identity:
            Used to identify recipient of worker
        name:
            Used to identify the rpc-callable
        args:
            postions arguments of the rpc-callable
        kw:
            Keyword arguments of the rpc-callable
        """

    def create_timeout_detector(uuid):
        """
        Run in background a timeout task to terminate
        the future linked to given uuid
        """

    def cleanup_future(uuid, future):
        """
        Destroy the future kept in memory if any.
        """

    def on_socket_ready(message):
        """
        Main handler. This method is reponsible to handle every
        incomimg messages to the socket.
        """

    def register_rpc(func=None, name=None, env='default',
                     registry=registry):
        """
        decorator to register rpc endpoint only for this RPC instance.
        """

    def start():
        """
        Run all background tasks, plugins included.
        """

    def stop():
        """
        Stop all background tasks, plugins included.
        """

    def read_forever(socket, callback):
        """
        Helper method that plugins can use to
        call callback each time the given socket receive a message
        """

    def create_periodic_callback(callback, timer):
        """
        Execute callback every `timer` seconds.
        """

    def create_later_callback(callback, timer):
        """
        Execute callback once in `timer` seconds.
        """

    def timeout_task(uuid):
        """
        Mark future identified by uuid as Timeout and resume blocking call
        """


class IClient(IBaseRPC):
    """
    Interface for Clients
    """


class IServer(IBaseRPC):
    """
    Interface for Servers
    """


class IHeartbeatBackend(zope.interface.Interface):
    """
    Interface for heartbeat backend
    """
    def handle_heartbeat(peer_id):
        """
        Called when an Hearbeat is received from given
        peer_id
        """

    def handle_timeout(peer_id):
        """
        Called when a time is detected for given peer_id
        """

    def configure():
        """
        """

    def stop():
        """
        """


class IRPCCallable(zope.interface.Interface):
    """
    Wrapper around callable.
    Allow to specify a name for the rpc-callable
    and an applicable environment to check perimissions.
    """
    func = zope.interface.Attribute("""
        real callable
        """)
    name = zope.interface.Attribute("""
        name of rpc-callable
        """)
    env = zope.interface.Attribute("""
        name of Predicate environment
        """)

    def __call__(*args, **kw):
        """
        Run rpc-callable
        """

    def test(*args, **kw):
        """
        find a predicate for environment, and call-it
        to know if rpc-callable is allowed to be ran.
        """


class IRPCRoute(zope.interface.Interface):
    """
    Just an identifier for registered rpc-callable
    """


class IPredicate(zope.interface.Interface):
    """
    Responsible to allow or discard execution of
    rcp-callable for given context
    """
    def test(*args, **kw):
        """
        Must return boolean
        """
