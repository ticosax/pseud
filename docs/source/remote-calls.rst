Remote Calls
============

To perform remote procedure calls you just need to connect two peers, and
then, on your local peer instance, call a registered function with the right
parameters. You will then receive the return value of the remotely executed
function.

.. code:: python

   # server.py
   import string

   import gevent
   import pseud
   from pseud.utils import register_rpc


   server = pseud.Server('remote')
   server.bind('tcp://127.0.0.1:5555')

   # register locally for this server only
   server.register_rpc(string.lower)
   # register globally for all rpc instances
   register_rpc(string.upper)

   server.start()
   gevent.wait()

.. code:: python

   # client.py
   import pseud


   client = pseud.Client('remote')
   client.connect('tcp://127.0.0.1:5555')

   future1 = client.lower('ABC')
   future2 = client.upper('def')

   assert future1.get() == 'abc'
   assert future2.get() == 'DEF'

Registration
++++++++++++

Registration is a necessary step to control what callable you want to expose
for remote peers.

Global
~~~~~~

The `register_rpc` decorator from :mod:`pseud.utils` module must be used to
register a callable for all workers of the current process.

.. code:: python

   from pseud.utils import regsiter_rpc


   @register_rpc
   def call_me():
        return 'Done'

Local
~~~~~

An RPC instance exposes its own `register_rpc` function, which is used to 
register a callable only for that same RPC instance.

.. code:: python

   def call_me():
       return 'Done'

   server.register_rpc(call_me)

You can also instantiate a registry and give it to
:mod:`pseud.utils.register_rpc`, and pass it as an init parameter in the RPC.
It is more convenient to use register_rpc as a decorator

.. code:: python

   import pseud
   from pseud.utils import register_rpc, create_local_registry

   registry = create_local_registry('worker')

   @register_rpc(registry=registry)
   def call_me():
       return 'Done'

   server = pseud.Server('worker', registry=registry)

Name it !
~~~~~~~~~

You can also decide to provide your own name (dotted name) to the callable


.. code:: python

   from pseud.utils import regsiter_rpc


   @register_rpc('this.is.a.name')
   def call_me():
        return 'Done'

.. code:: python

   client.this.is.a.name().get() == 'Done'

Server wants to make the client do work
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In order to let the server send jobs to its connected clients, the caller
should know the identity of the specified client beforehand.
By default all clients are anonymous for the server. This is why it
is necessary to rely on your own ``security_plugin`` to perform
the authentication.

The most simple authentication that you can use is ``plain`` for the client,
by passing ``user_id`` and ``password`` arguments to the constructor.
Then on the server side ``trusted_peer`` will just trust that given ``user_id``
will identify the peer, and ignore the password.

Given a client whose identity is ``'client1'``, with a registered function named
``addition``, the following statement may be used to send work from the server
to the client:

.. code:: python

   # server.py
   server = Server('service', security_plugin='trusted_peer')
   server.bind('tcp://127.0.0.1:5555')
   server.start()

.. code:: python

   # client.py
   client = Client('service',
                    security_plugin='plain',
                    user_id='client1',
                    password='')

   client.connect('tcp://127.0.0.1:5555')

   @client.register_rpc
   def addition(a, b):
       return a + b

   client.hello('Me')  # perform a first call to register itself

.. note::

    The client needs to perform at least one call to the server
    to register itself. Otherwise the server won't know a client is connected
    to it. On real condition the heartbeat backend will take care of it.
    So you do not have to worry about it.

.. code:: python

   # server.py

   # gevent api
   server.send_to('client1').addition(2, 4).get() == 6

.. note::

    the ``client1`` string is the user_id provided by the client.
