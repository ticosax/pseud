import functools
import itertools
import uuid

import tornado
import zmq
from zmq.eventloop import ioloop
import zope.component
import zope.interface

from .interfaces import (IClient,
                         IHeartbeatBackend,
                         IServer,
                         HEARTBEAT,
                         VERSION)

from .utils import register_heartbeat_backend


class _BaseHeartbeatBackend(object):

    def __init__(self, rpc):
        self.rpc = rpc


@register_heartbeat_backend
@zope.interface.implementer(IHeartbeatBackend)
@zope.component.adapter(IClient)
class NoOpHeartbeatBackendForClient(_BaseHeartbeatBackend):
    name = 'noop_heartbeat_backend'

    def handle_heartbeat(self, peer_id):
        pass

    def handle_timeout(self, peer_id):
        pass

    def configure(self):
        pass

    def stop(self):
        pass


@register_heartbeat_backend
@zope.interface.implementer(IHeartbeatBackend)
@zope.component.adapter(IServer)
class NoOpHeartbeatBackendForServer(_BaseHeartbeatBackend):
    name = 'noop_heartbeat_backend'

    def handle_timeout(self, peer_id):
        pass

    def handle_heartbeat(self, peer_id):
        pass

    def configure(self):
        pass

    def stop(self):
        pass


@register_heartbeat_backend
@zope.interface.implementer(IHeartbeatBackend)
@zope.component.adapter(IClient)
class TestingHeartbeatBackendForClient(_BaseHeartbeatBackend):
    name = 'testing_heartbeat_backend'

    def handle_timeout(self, peer_id):
        pass

    def handle_heartbeat(self, peer_id):
        uid = uuid.uuid4().bytes
        self.rpc.stream.send_multipart([self.rpc.peer_identity, VERSION,
                                        uid, HEARTBEAT, ''])

    def configure(self):
        self.periodic_callback = tornado.ioloop.PeriodicCallback(
            functools.partial(self.handle_heartbeat, self.rpc.identity),
            callback_time=100,
            io_loop=self.rpc.io_loop
        )
        print 'Heartbeat starting'
        self.periodic_callback.start()

    def stop(self):
        print 'stop TestingHeartbeatBackendForClient'
        self.periodic_callback.stop()


@register_heartbeat_backend
@zope.interface.implementer(IHeartbeatBackend)
@zope.component.adapter(IServer)
class TestingHeartbeatBackendForServer(_BaseHeartbeatBackend):
    name = 'testing_heartbeat_backend'
    max_time_before_dead = 200
    callback_pool = {}

    def handle_timeout(self, peer_id):
        callback = self.callback_pool.pop(peer_id)
        callback.stop()
        callback = None
        self.monitoring_socket.send('Gone {!r}'.format(peer_id))

    def handle_heartbeat(self, peer_id):
        self.monitoring_socket.send(peer_id)
        previous = self.callback_pool.pop(peer_id, None)
        if previous is not None:
            previous.stop()
            previous = None
        callback = self.callback_pool[peer_id] = ioloop.DelayedCallback(
            functools.partial(self.handle_timeout, peer_id),
            self.max_time_before_dead,
            io_loop=self.rpc.io_loop)
        callback.start()

    def configure(self):
        self.monitoring_socket = self.rpc.context.socket(zmq.PUB)
        self.monitoring_socket.bind('inproc://testing_heartbeating_backend')

    def stop(self):
        print 'stop TestingHeartbeatBackendForServer'
        self.monitoring_socket.close()
        itertools.imap(lambda c: c.stop(), self.callback_pool.itervalues())
