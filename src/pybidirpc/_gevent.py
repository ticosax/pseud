import gevent
import zmq.green as zmq
import zope.interface

from .common import BaseRPC
from .interfaces import IClient, IServer


class GeventBaseRPC(BaseRPC):

    def _make_context(self):
        return zmq.Context.instance()

    def _backend_init(self, io_loop=None):
        pass

    def _send_work(self, peer_identity, name, *args, **kw):
        message, uid = self._prepare_work(peer_identity, name, *args, **kw)
        print 'sending work', message
        self.auth_backend.save_last_work(message)
        gevent.spawn(self.socket.send_multipart, message)
        print 'work sent'
        # XXX make sure we destroy the future if no answer is comming
        self.future_pool[uid] = future = gevent.event.AsyncResult()
        self.start()
        return future

    def _store_result_in_future(self, future, result):
        future.set(result)

    def _receiver(self):
        while True:
            request = self.socket.recv_multipart()
            self.on_socket_ready(request)

    def start(self):
        self.receiver = gevent.spawn(self._receiver)
        gevent.sleep(.1)

    def stop(self):
        self.receiver.kill()
        self.auth_backend.stop()
        self.heartbeat_backend.stop()

    def _prepare_stream(self):
        pass


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
