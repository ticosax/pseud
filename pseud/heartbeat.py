import asyncio
import contextlib
import logging

import zmq
import zope.component
import zope.interface

from .common import handle_result
from .interfaces import (IClient,
                         IHeartbeatBackend,
                         IServer,
                         HEARTBEAT,
                         VERSION)

from .utils import register_heartbeat_backend

logger = logging.getLogger(__name__)

__all__ = ['NoOpHeartbeatBackendForClient', 'NoOpHeartbeatBackendForServer']


class _BaseHeartbeatBackend(object):

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


@register_heartbeat_backend
@zope.interface.implementer(IHeartbeatBackend)
@zope.component.adapter(IClient)
class TestingHeartbeatBackendForClient(_BaseHeartbeatBackend):
    name = 'testing_heartbeat_backend'

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


@register_heartbeat_backend
@zope.interface.implementer(IHeartbeatBackend)
@zope.component.adapter(IServer)
class TestingHeartbeatBackendForServer(_BaseHeartbeatBackend):
    name = 'testing_heartbeat_backend'
    timeout = .2
    task_pool = {}

    async def handle_timeout(self, user_id, routing_id):
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

        self.task_pool[user_id] = self.rpc.loop.call_later(
            self.timeout,
            lambda: asyncio.ensure_future(
                self.handle_timeout(user_id, routing_id)))

    def configure(self):
        self.monitoring_socket = self.rpc.context.socket(zmq.PUB)
        self.monitoring_socket.bind(b'ipc://testing_heartbeating_backend')

    async def stop(self):
        self.monitoring_socket.close(linger=0)
        for task in self.task_pool.values():
            task.cancel()
