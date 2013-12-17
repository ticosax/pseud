import tornado.concurrent
import tornado.gen
import zmq
from zmq.eventloop import ioloop, zmqstream
import zope.interface

from .common import BaseRPC
from .interfaces import IClient, IServer

ioloop.install()


def async_sleep(io_loop, duration):
    return tornado.gen.Task(
        io_loop.add_timeout,
        io_loop.time() + duration)


class TornadoBaseRPC(BaseRPC):
    def _make_context(self):
        return zmq.Context.instance()

    def _backend_init(self, io_loop=None):
        self.internal_loop = False
        if io_loop is None:
            self.internal_loop = True
            self.io_loop = ioloop.IOLoop.instance()
        else:
            self.io_loop = io_loop

    @tornado.gen.coroutine
    def _send_work(self, peer_identity, name, *args, **kw):
        message, uid = self._prepare_work(peer_identity, name, *args, **kw)
        print 'sending work', message
        self.auth_backend.save_last_work(message)
        yield tornado.gen.Task(self.stream.send_multipart, message)
        print 'work sent'
        self.future_pool[uid] = future = tornado.concurrent.Future()
        self.io_loop.add_future(future,
                                functools.partial(self._cleanup_future, uid))
        yield self.start()
        raise tornado.gen.Return(future)

    def _cleanup_future(self, uuid, future):
        try:
            del self.future_pool[uuid]
        except KeyError:
            pass

    def _store_result_in_future(self, future, result):
        future.set_result(result)

    @tornado.gen.coroutine
    def start(self):
        self.stream.on_recv(self.on_socket_ready)
        # Warmup delay !!
        yield async_sleep(self.io_loop, .1)
        if self.internal_loop:
            print self.__class__.__name__, 'ready'
            yield self.io_loop.start()

    def _prepare_stream(self):
        self.stream = zmqstream.ZMQStream(self.socket, self.io_loop)

    def stop(self):
        self.stream.on_recv(None)
        self.stream.flush()
        self.stream.close()
        self.auth_backend.stop()
        self.heartbeat_backend.stop()
        if self.internal_loop:
            self.io_loop.stop()


@zope.interface.implementer(IClient)
class Client(TornadoBaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, identity, peer_identity, context_module_name=None,
                 context=None, io_loop=None,
                 security_plugin='noop_auth_backend', timeout=5,
                 public_key=None, private_key=None, peer_public_key=None,
                 password=None,
                 heartbeat_plugin='noop_heartbeat_backend',
                 ):
        super(Client, self).__init__(identity, peer_identity=peer_identity,
                                     context_module_name=context_module_name,
                                     context=context, io_loop=io_loop,
                                     security_plugin=security_plugin,
                                     timeout=timeout, public_key=public_key,
                                     private_key=private_key,
                                     peer_public_key=peer_public_key,
                                     password=password,
                                     heartbeat_plugin=heartbeat_plugin,
                                     )


@zope.interface.implementer(IServer)
class Server(TornadoBaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, identity, context_module_name=None,
                 context=None, io_loop=None,
                 security_plugin='noop_auth_backend', timeout=5,
                 private_key=None, public_key=None,
                 heartbeat_plugin='noop_heartbeat_backend'):
        super(Server, self).__init__(identity,
                                     context_module_name=context_module_name,
                                     context=context, io_loop=io_loop,
                                     security_plugin=security_plugin,
                                     timeout=timeout,
                                     public_key=public_key,
                                     private_key=private_key,
                                     heartbeat_plugin=heartbeat_plugin)
