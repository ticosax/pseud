import functools
import zope.component
import zope.interface

from .interfaces import (IAuthenticationBackend,
                         IHeartbeatBackend,
                         IRPCCallable,
                         IRPCRoute,
                         ServiceNotFoundError,
                         IPredicate,
                         )


registry = zope.component.getGlobalSiteManager()


def register_auth_backend(cls):
    """
    Decorator to register Authentication Backend plugins
    """
    registry.registerAdapter(cls, zope.component.adaptedBy(cls),
                             IAuthenticationBackend,
                             cls.name)
    return cls


def register_heartbeat_backend(cls):
    """
    Decorator to register Heartbeat Backend plugins
    """
    registry.registerAdapter(cls, zope.component.adaptedBy(cls),
                             IHeartbeatBackend,
                             cls.name)
    return cls


def register_predicate(cls):
    """
    Decorator to register Predicate plugins
    """
    registry.registerAdapter(cls, zope.component.adaptedBy(cls),
                             IPredicate,
                             cls.name)
    return cls


def create_local_registry(name):
    """
    Helper function to create a custom
    :py:class:`registry <zope.interface.registry.Components>`
    """
    return zope.interface.registry.Components(name=name, bases=(registry,))


@zope.interface.implementer(IRPCCallable)
class RPCCallable(object):
    def __init__(self, func, name, domain='default'):
        self.func = func
        self.name = name
        self.domain = domain

    def __call__(self, *args, **kw):
        return self.func(*args, **kw)

    def test(self, *args, **kw):
        return zope.component.getAdapter(self,
                                         IPredicate,
                                         name=self.domain).test(*args, **kw)


def register_rpc(func=None, name=None, domain='default', registry=registry):
    def wrapper(fn):
        endpoint_name = name or fn.func_name
        registered_name = '{}:{}'.format(endpoint_name, domain)
        registry.registerUtility(RPCCallable(fn, name=endpoint_name,
                                             domain=domain),
                                 IRPCRoute,
                                 name=registered_name)
        return fn

    if callable(func):
        return wrapper(func)
    return wrapper


def get_rpc_callable(name, registry=registry, *args, **kw):
    """
    Supports predicate API (check like checking permissions)
    TODO improve sorting
    """
    for rpc_call in sorted(registry.getAllUtilitiesRegisteredFor(
            IRPCRoute), key=lambda c: c.domain == 'default', reverse=False):
        if rpc_call.name != name:
            continue
        if rpc_call.test(*args, **kw):
            return rpc_call
    raise ServiceNotFoundError(name)
