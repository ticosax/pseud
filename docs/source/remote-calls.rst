Remote Calls
============

To perform remote procedure calls you just need to connect two peers, and then
call on your local peer instance a registered function with right parameters.
You will then receive the return value of this function executed remotely.

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

It is a procedure that is necessary to control what callable you want to expose
for remote peers.

Global
~~~~~~

The `register_rpc` decorator from :mod:`pseud.utils` module must be used to
register callable for all workers of current process.

.. code:: python

   from pseud.utils import regsiter_rpc


   @register_rpc
   def call_me():
        return 'Done'

Local
~~~~~

Each RPC instance expose its own `register_rpc` function that is used to
register a callable for this RPC instance only.

.. code:: python

   def call_me():
       return 'Done'

   server.register_rpc(call_me)

Also as a more advance usage, you can instantiate a registry and give it to
:mod:`pseud.utils.register_rpc` and as init parameter of the RPC.
It is more convenient to use register_rpc as decorator

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

Server wants to make client working
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In order to let the server jobs to its connected clients.
The caller should know before the identity of the specified client.
How to get list of currently connected client is described
in :ref:`heartbeating` section.

Assuming we know the client identity `'client'` and the client
register a function named `addition`, then the server can send
work to the client with the following statement ::

   # gevent process
   server.send_to('client').addition(2, 4).get() == 6


Predicates
++++++++++

During registration, user can associate a domain to the callable.
Each domain will be linked to a specific Predicate with its own Policy.
By default all rpc-callable are registered within `default` domain, that allow
all callable to be called.
In case of rejection, :mod:`pseud.interfaces.ServiceNotFoundError` exception
will be raised.

You can of course define your own predicate and register some callable under
restricted domain for instance.

.. code:: python

   @register_rpc(name='try_to_call_me')
   def callme(*args, **kw):
       return 'small power'

   @register_rpc(name='try_to_call_me',
                 domain='restricted')
   def callme_admin(*args, **kw):
       return 'great power'

In this example we have 2 callable registered with same name but with
different domain.
Assuming we a have a Authentication Backend that is able to return a user
instance and from this user instance we can know if he is admin.
then we can assume the following behaviour ::

    # gevent client + user lambda

    client.try_to_callme().get() == 'small power'

Then with user with admin rights ::

    # gevent client + user admin

    client.try_to_callme().get() == 'great power'

From this behaviour we can perform routing based on user permissions.
