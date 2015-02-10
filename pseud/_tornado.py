from collections import Counter
import functools
import logging
import pprint
import sys
import traceback

from concurrent.futures import TimeoutError
try:
    from tornado.concurrent import FUTURES
except ImportError:
    import tornado.concurrent
    future_class = tornado.concurrent.Future
    FUTURES = [future_class]
else:
    future_class = FUTURES[0]
import tornado.gen
import zmq
from zmq.eventloop import ioloop, zmqstream
import zope.interface

from .common import BaseRPC
from .interfaces import (
    IClient,
    IServer,
    EMPTY_DELIMITER,
    ERROR,
    OK,
    ServiceNotFoundError,
    VERSION,
)
from .utils import get_rpc_callable

ioloop.install()

logger = logging.getLogger(__name__)


MAX_EHOSTUNREACH_RETRY = 2


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
            self.io_loop = ioloop.IOLoop()
        else:
            self.io_loop = io_loop

    @tornado.gen.coroutine
    def _handle_work_proxy(self, locator, args, kw, user_id, message_uuid):
        worker_callable = get_rpc_callable(
            locator,
            registry=self.registry,
            **self.auth_backend.get_predicate_arguments(user_id))
        if worker_callable.with_identity:
            result = worker_callable(user_id, *args, **kw)
        else:
            result = worker_callable(*args, **kw)
        if isinstance(result, FUTURES):
            result = yield result
            raise tornado.gen.Return(result)
        else:
            raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def _handle_work(self, message, routing_id, user_id, message_uuid):
        locator, args, kw = self.packer.unpackb(message)
        try:
            try:
                result = yield self._handle_work_proxy(
                    locator, args, kw, user_id, message_uuid)
            except ServiceNotFoundError:
                if self.proxy_to is None:
                    raise
                else:
                    result = yield self.proxy_to._handle_work_proxy(
                        locator, args, kw, user_id, message_uuid)

        except Exception:
            logger.exception('Pseud job failed')
            exc_type, exc_value = sys.exc_info()[:2]
            traceback_ = traceback.format_exc()
            name = exc_type.__name__
            message = str(exc_value)
            result = (name, message, traceback_)
            status = ERROR
        else:
            status = OK
        response = self.packer.packb(result)
        message = [routing_id, EMPTY_DELIMITER, VERSION, message_uuid, status,
                   response]
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Worker send reply {!r} {}'.format(
                message[:-1],
                pprint.pformat(result))
            )
        self.send_message(message)

    def send_work(self, user_id, name, *args, **kw):
        self.start()
        message, uid = self._prepare_work(user_id, name, *args, **kw)
        self.future_pool[uid] = future = future_class()
        self.create_timeout_detector(uid)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Sending work: {!r} {}'.format(
                message[:-1],
                pprint.pformat(self.packer.unpackb(message[-1]))))
        self.auth_backend.save_last_work(message)
        self.send_message(message)
        self.io_loop.add_future(future,
                                functools.partial(self.cleanup_future, uid))
        return future

    def _retry(self, msg):
        self.send_message(msg)

    def send_callback(self, counter, msg, status):
        if (isinstance(status, zmq.ZMQError) and
                status.errno == zmq.EHOSTUNREACH):
            # ROUTER does not know yet the recipient
            if counter[msg[0]] > MAX_EHOSTUNREACH_RETRY:
                return
            counter[msg[0]] += 1
            # retry in 100 ms
            self.create_later_callback(functools.partial(self._retry, msg), .1)

    def send_message(self, message):
        self.reader.send_multipart(message)

    def _store_result_in_future(self, future, result):
        future.set_result(result)

    @tornado.gen.coroutine
    def start(self):
        if self.reader is None:
            self.reader = self.read_forever(self.socket,
                                            self.on_socket_ready)
        if self.internal_loop:
            logger.debug('{} started'.format(self.__class__.__name__))
            self.io_loop.start()

    def read_forever(self, socket, callback, copy=False):
        stream = zmqstream.ZMQStream(socket,
                                     io_loop=self.io_loop)
        stream.on_recv(callback, copy=copy)
        stream.on_send(functools.partial(self.send_callback, Counter()))
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
        try:
            self.future_pool[uuid].set_exception(TimeoutError())
        except KeyError:
            pass

    def stop(self):
        if self.reader is not None:
            self.reader.on_recv(None)
            self.reader.flush()
            self.reader.close()
            self.reader = None
        if not self.socket.closed:
            self.socket.close(linger=0)
        self.auth_backend.stop()
        self.heartbeat_backend.stop()
        if self.internal_loop:
            self.io_loop.stop()


@zope.interface.implementer(IClient)
class Client(TornadoBaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, peer_routing_id, routing_id=None, **kw):
        if routing_id:
            raise TypeError('routing_id argument is prohibited')
        super(Client, self).__init__(peer_routing_id=peer_routing_id, **kw)


@zope.interface.implementer(IServer)
class Server(TornadoBaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, user_id, routing_id=None, **kw):
        if routing_id:
            raise TypeError('routing_id argument is prohibited')
        super(Server, self).__init__(user_id=user_id, routing_id=user_id, **kw)
