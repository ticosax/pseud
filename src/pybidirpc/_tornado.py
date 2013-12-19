import functools
import logging

from concurrent.futures import TimeoutError
import tornado.concurrent
import tornado.gen
import zmq
from zmq.eventloop import ioloop, zmqstream
import zope.interface

from .common import BaseRPC
from .interfaces import IClient, IServer

ioloop.install()

logger = logging.getLogger(__name__)


def async_sleep(io_loop, duration):
    return tornado.gen.Task(
        io_loop.add_timeout,
        io_loop.time() + duration)


class TornadoBaseRPC(BaseRPC):
    def _make_context(self):
        return zmq.Context.instance()

    def _backend_init(self, io_loop=None):
        self.reader = None
        self.internal_loop = False
        if io_loop is None:
            self.internal_loop = True
            self.io_loop = ioloop.IOLoop.instance()
        else:
            self.io_loop = io_loop

    @tornado.gen.coroutine
    def send_work(self, peer_identity, name, *args, **kw):
        yield self.start()
        message, uid = self._prepare_work(peer_identity, name, *args, **kw)
        self.future_pool[uid] = future = tornado.concurrent.Future()
        self.create_timeout_detector(uid)
        logger.debug('Sending work: {!r}'.format(message))
        self.auth_backend.save_last_work(message)
        self.send_message(message)
        logger.debug('Work sent')
        self.io_loop.add_future(future,
                                functools.partial(self.cleanup_future, uid))
        raise tornado.gen.Return(future)

    @tornado.gen.coroutine
    def send_message(self, message):
        yield tornado.gen.Task(self.reader.send_multipart, message)

    def _store_result_in_future(self, future, result):
        future.set_result(result)

    @tornado.gen.coroutine
    def start(self):
        if self.reader is None:
            self.reader = self.read_forever(self.socket,
                                            self.on_socket_ready)
        # Warmup delay !!
        yield async_sleep(self.io_loop, .1)
        if self.internal_loop:
            logger.debug('{} sent'.format(self.__class__.__name__))
            yield self.io_loop.start()

    def read_forever(self, socket, callback):
        stream = zmqstream.ZMQStream(socket,
                                     io_loop=self.io_loop)
        stream.on_recv(callback)
        return stream

    def create_periodic_callback(self, callback, timer):
        periodic_callback = tornado.ioloop.PeriodicCallback(
            callback,
            callback_time=timer * 1000,
            io_loop=self.io_loop)
        periodic_callback.start()
        return periodic_callback

    def create_later_callback(self, callback, timer):
        return self.io_loop.add_timeout(
            self.io_loop.time() + timer,
            callback)

    def timeout_task(self, uuid):
        self.future_pool[uuid].set_exception(TimeoutError)

    def stop(self):
        if self.reader is not None:
            self.reader.on_recv(None)
            self.reader.flush()
            self.reader.close()
            self.reader = None
        self.auth_backend.stop()
        self.heartbeat_backend.stop()
        if self.internal_loop:
            self.io_loop.stop()


@zope.interface.implementer(IClient)
class Client(TornadoBaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, identity, peer_identity, context_module_name='',
                 context=None, io_loop=None,
                 security_plugin='noop_auth_backend', timeout=5,
                 public_key=None, secret_key=None, peer_public_key=None,
                 password=None,
                 heartbeat_plugin='noop_heartbeat_backend',
                 ):
        super(Client, self).__init__(identity, peer_identity=peer_identity,
                                     context_module_name=context_module_name,
                                     context=context, io_loop=io_loop,
                                     security_plugin=security_plugin,
                                     timeout=timeout, public_key=public_key,
                                     secret_key=secret_key,
                                     peer_public_key=peer_public_key,
                                     password=password,
                                     heartbeat_plugin=heartbeat_plugin,
                                     )


@zope.interface.implementer(IServer)
class Server(TornadoBaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, identity, context_module_name='',
                 context=None, io_loop=None,
                 security_plugin='noop_auth_backend', timeout=5,
                 secret_key=None, public_key=None,
                 heartbeat_plugin='noop_heartbeat_backend'):
        super(Server, self).__init__(identity,
                                     context_module_name=context_module_name,
                                     context=context, io_loop=io_loop,
                                     security_plugin=security_plugin,
                                     timeout=timeout,
                                     public_key=public_key,
                                     secret_key=secret_key,
                                     heartbeat_plugin=heartbeat_plugin)
