import logging

import zope.component
import zope.interface

from .interfaces import (
    IAuthenticationBackend,
    IClient,
    IServer,
)
from .utils import register_auth_backend

logger = logging.getLogger(__name__)


class _BaseAuthBackend:

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

    async def stop(self):
        pass

    def configure(self):
        pass

    async def handle_hello(self, *args):
        pass

    async def handle_authenticated(self, message):
        pass

    def is_authenticated(self, peer_id):
        return True

    def save_last_work(self, message):
        pass

    def get_predicate_arguments(self, peer_id):
        return {}

    def get_routing_id(self, user_id):
        return user_id

    def register_routing_id(self, user_id, routing_id):
        pass


@register_auth_backend
@zope.interface.implementer(IAuthenticationBackend)
@zope.component.adapter(IServer)
class NoOpAuthenticationBackendForServer(NoOpAuthenticationBackendForClient):
    pass
