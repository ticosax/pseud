.. _heartbeating:

Heartbeating
============

pseud allows you to build your own Heartbeat Backend.
Your implementation must conform to its
:py:class:`Interface <zope.interface.Interface>` defined in
:py:class:`pseud.interfaces.IHeartbeatBackend`

Also all your plugin must :py:func:`adapts <zope.component.adapts>` :py:class:`pseud.interfaces.IClient` or
:py:class:`pseud.interfaces.IServer` and being registered thanks to
:py:func:`pseud.utils.register_heartbeat_backend` decorator.

Heartbeat backends aim to define your the policy you need regarding exclusion
of disconnected peer, e.g.. after 3 heartbeat missed, you can decide to exclude
peer from list of known connected peers.

Also, very important, thanks to heartbeat backends you can maintain an accurate
list of currently connected clients and their ids. It is up to you to decide to store this
list in memory (simple dict), or to use redis if you think the number of peers
will be huge.


You can start with the following snippet ::

    @register_heartbeat_backend
    @zope.interface.implementer(IHeartbeatBackend)
    @zope.component.adapter(IClient)
    class MyHeartbeatBackend(object):
        name = 'my_heartbeat_backend'

        def __init__(self, rpc):
            self.rpc = rpc

        def handle_heartbeat(self, user_id, routing_id):
            pass

        def handle_timeout(self, user_id, routing_id):
            pass

        def configure(self):
            pass

        def stop(self):
            pass

In this example the name `'my_heartbeat_backend'` will be used when
instanciating your RPC endpoint.

.. code:: python

    client = pseud.Client('remote',
                          heartbeat_plugin='my_heartbeat_backend')


Read :ref:`protocol` for more explanation. Also in :mod:`pseud.heartbeat`
you will find examples that are used in tests.
