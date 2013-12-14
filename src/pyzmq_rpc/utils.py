import tornado.gen
import zope.component
import zope.interface

from .interfaces import IAuthenticationBackend, IHeartbeatBackend


class peer_identity_provider(object):

    def __init__(self, server, peer_identity):
        self.server = server
        self.peer_identity = peer_identity

    def __enter__(self):
        self.server.peer_identity = self.peer_identity

    def __exit__(self, *args):
        self.server.peer_identity = None


def async_sleep(io_loop, duration):
    return tornado.gen.Task(
        io_loop.add_timeout,
        io_loop.time() + duration)


registry = zope.component.getGlobalSiteManager()


def register_auth_backend(cls):
    registry.registerAdapter(cls, zope.component.adaptedBy(cls),
                             IAuthenticationBackend,
                             cls.name)
    return cls


def register_heartbeat_backend(cls):
    registry.registerAdapter(cls, zope.component.adaptedBy(cls),
                             IHeartbeatBackend,
                             cls.name)
    return cls
