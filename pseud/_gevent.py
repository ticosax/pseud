import functools
import logging
import pprint

import gevent
from gevent.timeout import Timeout
import zmq.green as zmq
import zope.interface

from .common import BaseRPC, msgpack_unpackb
from .interfaces import IClient, IServer


logger = logging.getLogger(__name__)


def periodic_loop(callback, timer):
    while True:
        gevent.sleep(timer)
        gevent.spawn(callback)


def forever_loop(socket, callback):
    while True:
        message = socket.recv_multipart()
        gevent.spawn(callback, message)


class GeventBaseRPC(BaseRPC):

    def _make_context(self):
        return zmq.Context.instance()

    def _backend_init(self, io_loop=None):
        self.io_loop = None

    def send_work(self, peer_identity, name, *args, **kw):
        message, uid = self._prepare_work(peer_identity, name, *args, **kw)
        self.create_timeout_detector(uid)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Sending work: {!r} {!r}'.format(
                message[:-1],
                pprint.pformat(msgpack_unpackb(message[-1]))))
        self.auth_backend.save_last_work(message)
        self.start()
        self.send_message(message)
        self.future_pool[uid] = future = gevent.event.AsyncResult()
        future.rawlink(functools.partial(self.cleanup_future, uid))
        return future

    def send_message(self, message):
        gevent.spawn(self.socket.send_multipart, message)

    def _store_result_in_future(self, future, result):
        future.set(result)

    def start(self):
        if self.reader is None:
            self.reader = self.read_forever(self.socket,
                                            self.on_socket_ready)
            gevent.sleep(.1)

    def stop(self):
        if self.reader is not None:
            self.reader.kill()
        if not self.socket.closed:
            self.socket.linger = 0
            self.socket.close()
        self.auth_backend.stop()
        self.heartbeat_backend.stop()

    def read_forever(self, socket, callback):
        return gevent.spawn(forever_loop, socket, callback)

    def create_periodic_callback(self, callback, timer):
        return gevent.spawn(periodic_loop, callback, timer)

    def create_later_callback(self, callback, timer):
        return gevent.spawn_later(timer, callback)

    def timeout_task(self, uuid):
        try:
            self.future_pool[uuid].set_exception(Timeout)
        except KeyError:
            pass


@zope.interface.implementer(IClient)
class Client(GeventBaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, peer_identity, **kw):
        super(Client, self).__init__(peer_identity=peer_identity,
                                     **kw)


@zope.interface.implementer(IServer)
class Server(GeventBaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, identity, **kw):
        super(Server, self).__init__(identity=identity, **kw)
