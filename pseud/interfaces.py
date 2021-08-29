# -*- coding: utf-8 -*-
import zope.interface


AUTHENTICATED = b'\x04'
ERROR = b'\x10'
HEARTBEAT = b'\x06'
HELLO = b'\x02'
OK = b'\x01'
UNAUTHORIZED = b'\x11'
WORK = b'\x03'

VERSION = b'v1'

EMPTY_DELIMITER = b''


class ServiceNotFoundError(Exception):
    pass


class UnauthorizedError(Exception):
    pass


class IAuthenticationBackend(zope.interface.Interface):

    rpc = zope.interface.Attribute("""
        RPC instance
        """)

    def configure():
        """
        Hook to adapt your RPC peer.
        Must be used to start any service like a zap_handler
        """

    async def stop():
        """
        Hook to stop any service running in background.
        Can be either IOLoop, threading, or multiprocess.
        """

    def handle_hello(user_id, routing_id, message_uuid, message):
        """
        This method is receiving information that has been asked
        to authenticate the peer. It can be for instance login/password
        in such case message is the password.
        This method must reply to the peer
        with a reply status of :term:`AUTHENTICATED` or
        :term:`UNAUTHORIZED`.

        .. code::

            self.rpc.send_message([routing_id, '', VERSION, message_uuid,
                                   AUTHENTICATED,
                                   'Welcome {!r}'.format(user_id)])
        """

    def handle_authenticated(message):
        """
        Called when rpc received acknowledgement of successful authentication.
        """

    def save_last_work(message):
        """
        Useful to resend the last work request, after sucessful
        authenctication challenge.
        """

    def is_authenticated(user_id):
        """
        Must return True or False and tell if rpc must challenge
        authentication for the current peer.
        """

    def get_predicate_arguments(user_id):
        """
        If predicates needs to filter callables
        based on identity of user.
        this is where you should provide additional keyword arguments
        that will be transmitted to :mod:`pseud.utils.get_rpc_callable`.
        Must return a dict.
        """

    def get_routing_id(user_id):
        """
        Must return the socket id associated to the given identity
        """

    def register_routing_id(user_id, routing_id):
        """
        Must handle mapping between routing_id and user_id
        for later use, when routing is asked knowing only user_id.
        """


class IBaseRPC(zope.interface.Interface):
    """
    All methods that an rpc service must support
    to handle pseud protocol
    """
    user_id = zope.interface.Attribute("""
        identity of current RPC.
        Will be used as routing_id for server.
        """)
    context = zope.interface.Attribute("""
        ØMQ context
        """)
    security_plugin = zope.interface.Attribute("""
        name of security backend to load
        """)
    public_key = zope.interface.Attribute("""
        Z85 encoded public key of the zeromq curve keypair
        """)
    secret_key = zope.interface.Attribute("""
        Z85 encoded private key of the zeromq curve keypair
        """)
    heartbeat_plugin = zope.interface.Attribute("""
        Name of the plugin used as heartbeat backend
        """)
    proxy_to = zope.interface.Attribute("""
        Must be another instance of RPC
        """)
    registry = zope.interface.Attribute("""
        Give your own registry or a new one will be built
        """)
    loop = zope.interface.Attribute("""
        Use given loop instance or create a new one.
        """)
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

    def send_work(user_id, name, *args, **kw):
        """
        Ask the peer to run specified task identified by name.

        peer_identity:
            Used to identify the worker
        name:
            Used to identify the rpc-callable
        args:
            positions arguments of the rpc-callable
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

    def register_rpc(func=None, name=None, domain='default',
                     registry=None):
        """
        decorator to register rpc endpoint only for this RPC instance.
        """

    async def start():
        """
        Run all background tasks, plugins included.
        """

    async def stop():
        """
        Stop all background tasks, plugins included.
        """

    def timeout_task(uuid):
        """
        Mark future identified by uuid as Timeout and resume blocking call
        """


class IClient(IBaseRPC):
    """
    Interface for Clients
    """
    peer_routing_id = zope.interface.Attribute("""
        routing_id of peer to communicate with
        """)
    peer_public_key = zope.interface.Attribute("""
        Z85 encoded public key of the zeromq curve
        keypair from remote peer
        """)
    password = zope.interface.Attribute("""
        If authentication is required by remote peer.
        `user_id`` will be the login.
        """)


class IServer(IBaseRPC):
    """
    Interface for Servers
    """


class IHeartbeatBackend(zope.interface.Interface):
    """
    Interface for heartbeat backend
    """

    rpc = zope.interface.Attribute("""
        RPC instance
        """)

    def handle_heartbeat(user_id, routing_id):
        """
        Called when an Hearbeat is received from given
        peer_id
        """

    async def handle_timeout(user_id, routing_id):
        """
        Called when a timeout is detected for given peer_id
        """

    def configure():
        """
        Prepare the plugin, called when rpc is starting
        """

    def stop():
        """
        Stop every tasks the plugin created in background
        """


class IRPCCallable(zope.interface.Interface):
    """
    Wrapper around callable.
    Allow to specify a name for the rpc-callable
    and an applicable domain to check perimissions.
    """
    func = zope.interface.Attribute("""
        Real callable
        """)
    name = zope.interface.Attribute("""
        Name of rpc-callable
        """)
    domain = zope.interface.Attribute("""
        Name of Predicate domain
        """)

    def __call__(*args, **kw):
        """
        Run rpc-callable
        """

    def test(*args, **kw):
        """
        Find a predicate for domain, and call-it
        to know if rpc-callable is allowed to be ran.
        Must return a boolean
        """


class IRPCRoute(zope.interface.Interface):
    """
    Just an identifier for registered rpc-callable
    """


class IPredicate(zope.interface.Interface):
    """
    Responsible to allow or discard execution of
    rpc-callable for given context
    """
    def test(*args, **kw):
        """
        Must return boolean
        """
