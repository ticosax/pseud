import logging

import zope.component
import zope.interface

from .interfaces import (IClient,
                         IHeartbeatBackend,
                         IServer,
                         )

from .utils import register_heartbeat_backend

logger = logging.getLogger(__name__)

__all__ = ['NoOpHeartbeatBackendForClient', 'NoOpHeartbeatBackendForServer']


class _BaseHeartbeatBackend:

    def __init__(self, rpc):
        self.rpc = rpc


@register_heartbeat_backend
@zope.interface.implementer(IHeartbeatBackend)
@zope.component.adapter(IClient)
class NoOpHeartbeatBackendForClient(_BaseHeartbeatBackend):
    """
    No op Heartbeat
    """
    name = 'noop_heartbeat_backend'

    async def handle_heartbeat(self, *args):
        pass

    async def handle_timeout(self, *args):
        pass

    def configure(self):
        pass

    async def stop(self):
        pass


@register_heartbeat_backend
@zope.interface.implementer(IHeartbeatBackend)
@zope.component.adapter(IServer)
class NoOpHeartbeatBackendForServer(_BaseHeartbeatBackend):
    """
    No op Heartbeat
    """
    name = 'noop_heartbeat_backend'

    async def handle_timeout(self, *args):
        pass

    async def handle_heartbeat(self, *args):
        pass

    def configure(self):
        pass

    async def stop(self):
        pass
