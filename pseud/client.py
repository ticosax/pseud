import asyncio
import builtins
import logging
import pprint
import uuid

import zmq
import zope.interface

from .common import BaseRPC, format_remote_traceback, internal_exceptions
from . import interfaces
from .interfaces import IClient, VERSION, WORK

logger = logging.getLogger(__name__)


@zope.interface.implementer(IClient)
class Client(BaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, peer_routing_id, routing_id=None, **kw):
        if routing_id:
            raise TypeError('routing_id argument is prohibited')
        super().__init__(peer_routing_id=peer_routing_id, **kw)


@zope.interface.implementer(IClient)
class SyncClient(BaseRPC):
    """
    Support limited features and run synchronously.
    Doesn't require a loop to be running.
    This is suitable to use in synchronous environment like
    within wsgi process.
    """
    socket_type = zmq.REQ

    def _make_context(self):
        return zmq.Context.instance()

    def send_work(self, peer_identity, name, *args, **kw):
        message, uid = self._prepare_work(name, *args, **kw)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Sending work: {!r} {}'.format(
                message[:-1],
                pprint.pformat(self.packer.unpackb(message[-1]))))
        response = self.send_message(message)
        return response

    def _prepare_work(self, name, *args, **kw):
        work = self.packer.packb((name, args, kw))
        uid = uuid.uuid4().bytes
        message = [VERSION, uid, WORK, work]
        return message, uid

    def _handle_ok(self, message, message_uuid):
        value = self.packer.unpackb(message)
        logger.debug('SyncClient result {!r} from {!r}'.format(value,
                                                               message_uuid))
        return value

    def _handle_error(self, message, message_uuid):
        value = self.packer.unpackb(message)
        klass, message, traceback = value
        full_message = '\n'.join((format_remote_traceback(traceback),
                                  message))
        try:
            exception = getattr(builtins, klass)(full_message)
        except AttributeError:
            if klass in internal_exceptions:
                raise getattr(interfaces, klass)(full_message)
            else:
                # Not stdlib Exception
                # fallback on something that expose informations received
                # from remote worker
                raise Exception('\n'.join((klass, full_message)))
        else:
            raise exception

    def send_message(self, message):
        self.socket.send_multipart(message)
        try:
            response = self.socket.recv_multipart(copy=False)
        except zmq.Again:
            raise asyncio.TimeoutError()
        return self.loop.run_until_complete(self.on_socket_ready(response))

    def _store_result_in_future(self, future, result):
        raise NotImplementedError('SyncClient can not do that')

    def connect(self, endpoint):
        self._setup_socket()
        self.socket.connect(endpoint)

    def start(self):
        pass

    def timeout_task(self, uuid):
        raise NotImplementedError('SyncClient can not do that')

    def stop(self):
        if not self.socket.closed:
            self.socket.linger = 0
            self.socket.close()
        self.loop.run_until_complete(self.auth_backend.stop())
        self.loop.run_until_complete(self.heartbeat_backend.stop())
