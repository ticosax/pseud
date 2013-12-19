import functools
import logging

import gevent
from gevent.timeout import Timeout
import zmq.green as zmq
import zope.interface

from .common import BaseRPC
from .interfaces import IClient, IServer


logger = logging.getLogger(__name__)


def periodic_loop(callback, timer):
    while True:
        gevent.sleep(timer)
        callback()


def forever_loop(socket, callback):
    while True:
        message = socket.recv_multipart()
        callback(message)


class GeventBaseRPC(BaseRPC):

    def _make_context(self):
        return zmq.Context.instance()

    def _backend_init(self, io_loop=None):
        self.io_loop = None

    def send_work(self, peer_identity, name, *args, **kw):
        message, uid = self._prepare_work(peer_identity, name, *args, **kw)
        self.create_timeout_detector(uid)
        logger.debug('Sending work: {!r}'.format(message))
        self.auth_backend.save_last_work(message)
        self.start()
        self.send_message(message)
        logger.debug('Work sent')
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
        if not self.socket.closed:
            self.socket.linger = 0
            self.socket.close()
        if self.reader is not None:
            self.reader.kill()
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

    def __init__(self, identity, peer_identity,
                 context=None, io_loop=None,
                 security_plugin='noop_auth_backend', timeout=5,
                 public_key=None, secret_key=None, peer_public_key=None,
                 password=None,
                 heartbeat_plugin='noop_heartbeat_backend',
                 proxy_to=None,
                 ):
        super(Client, self).__init__(identity, peer_identity=peer_identity,
                                     context=context, io_loop=io_loop,
                                     security_plugin=security_plugin,
                                     timeout=timeout, public_key=public_key,
                                     secret_key=secret_key,
                                     peer_public_key=peer_public_key,
                                     password=password,
                                     heartbeat_plugin=heartbeat_plugin,
                                     proxy_to=proxy_to,
                                     )


@zope.interface.implementer(IServer)
class Server(GeventBaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, identity,
                 context=None, io_loop=None,
                 security_plugin='noop_auth_backend', timeout=5,
                 secret_key=None, public_key=None,
                 heartbeat_plugin='noop_heartbeat_backend',
                 proxy_to=None
                 ):
        super(Server, self).__init__(identity,
                                     context=context, io_loop=io_loop,
                                     security_plugin=security_plugin,
                                     timeout=timeout,
                                     public_key=public_key,
                                     secret_key=secret_key,
                                     heartbeat_plugin=heartbeat_plugin,
                                     proxy_to=proxy_to,
                                     )
