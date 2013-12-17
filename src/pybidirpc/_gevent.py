import gevent
import zmq.green as zmq
import zope.interface

from .common import BaseRPC
from .interfaces import IClient, IServer


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
        pass

    def send_work(self, peer_identity, name, *args, **kw):
        message, uid = self._prepare_work(peer_identity, name, *args, **kw)
        print 'sending work', message
        self.auth_backend.save_last_work(message)
        self.send_message(message)
        print 'work sent'
        # XXX make sure we destroy the future if no answer is comming
        self.future_pool[uid] = future = gevent.event.AsyncResult()
        self.start()
        return future

    def send_message(self, message):
        gevent.spawn(self.socket.send_multipart, message)

    def _store_result_in_future(self, future, result):
        future.set(result)

    def start(self):
        self.reader = self.read_forever(self.socket,
                                        self.on_socket_ready)
        gevent.sleep(.1)

    def stop(self):
        self.socket.close()
        self.reader.kill()
        self.auth_backend.stop()
        self.heartbeat_backend.stop()

    def read_forever(self, socket, callback):
        return gevent.spawn(forever_loop, socket, callback)

    def create_periodic_callback(self, callback, timer):
        return gevent.spawn(periodic_loop, callback, timer)

    def create_later_callback(self, callback, timer):
        return gevent.spawn_later(timer, callback)


@zope.interface.implementer(IClient)
class Client(GeventBaseRPC):
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
class Server(GeventBaseRPC):
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