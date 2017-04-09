pseud
=====
.. image:: https://travis-ci.org/ticosax/pseud.svg?branch=master
   :target: https://travis-ci.org/ticosax/pseud
   :alt: Travis-CI Status

.. image:: https://codecov.io/gh/ticosax/pseud/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/ticosax/pseud
   :alt: Coverage Status

.. image:: https://readthedocs.org/projects/pseud/badge/?version=latest
   :target: http://pseud.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

Pythonic bidirectional-rpc API built on top of ØMQ with pluggable
encryption, authentication and heartbeating support.

Features
~~~~~~~~
#. ØMQ transport layer.
#. All native python types supported (msgpack).
#. First citizen exceptions.
#. Bi-bidirectional (server can initiate calls to connected clients).
#. Encryption based on CURVE.
#. Pluggable Authentication.
#. Pluggable Heartbeating.
#. Pluggable Remote Call Routing.
#. Built-in proxy support. A server can delegate the work to another one.
#. SyncClient (using zmq.REQ) to use within non event based processes.
   (Heartbeating, Authentication and job execution are not supported with
   the SyncClient.)

Installation
~~~~~~~~~~~~

Dependencies are declared in setup.py and all automatically installed, but,
pyzmq might build libzmq from bundled folder `OR` from your system wide libzmq.

libzmq 4.1 is now required. As it is not yet bundled within pyzmq you will
need to compile it yourself.

Then you can install latest pyzmq from pypi

.. code-block:: console

   $ pip install pyzmq --install-option="--zmq=/usr/local"


Execution
~~~~~~~~~

The Server
------------------

.. code-block:: python

    from pseud import Server


    server = Server('service')
    server.bind('tcp://127.0.0.1:5555')

    @server.register_rpc
    def hello(name):
        return 'Hello {0}'.format(name)

    await server.start()  # this will block forever


The Client
------------------

.. code-block:: python

    from pseud import Client


    client = Client('service', io_loop=loop)
    client.connect('tcp://127.0.0.1:5555')

    # Assume we are inside a coroutine
    async with client:
        response = await client.hello('Charly')
        assert response == 'Hello Charly'



The SyncClient
--------------

.. code-block:: python

   # to use within a non-asynchronous process or in a command interpreter
   from pseud import SyncClient


   client = SyncClient()
   client.connect('tcp://127.0.0.1:5555')

   async with client:
       assert client.hello('Charly') == 'Hello Charly'



The Server send a command to the client
---------------------------------------

It is important to note that the server needs to know which
peers are connected to it.
This is why the security_plugin ``trusted_peer`` comes handy.
It will register all peer id and be able to route messages to each of them.

.. code-block:: python

   from pseud import Server


   server = Server('service', security_plugin='trusted_peer')
   server.bind('tcp://127.0.0.1:5555')

   @server.register_rpc
   def hello(name):
       return 'Hello {0}'.format(name)

   await server.start()  # this will block forever

The client needs to send its identity to the server. This is why ``plain``
security plugin is used. The server will not check the password, he will just
take into consideration the user_id to perform the routing.


.. code-block:: python

   from pseud import Client


   client = Client('service',
                   security_plugin='plain',
                   user_id='alice',
                   password='')
   client.connect('tcp://127.0.0.1:5555')

   # Action that the client will perform when
   # requested by the server.
   @client.register_rpc(name='draw.me.a.sheep')
   def sheep():
       return 'beeeh'

   # The client needs to perform a first call
   # to the server in order to register itself.
   # on production this will be handle automatically
   # by the heartbeat backend. The first heartbeat will
   # trigger the authentication. Then until the client
   # disconnect the server will not ask the client
   # to reconnect.

   # assume we are inside a coroutine
   async with client:
        result = await client.hello('alice')
        assert result == 'Hello alice'

Back on server side, now the client as registered itself, we can send
to it any commands the client is able to do.

.. code-block:: python

    # assume we are inside a coroutine
    sheep = await server.send_to('alice').draw.me.a.sheep()
    assert sheep == 'beeeh'


Documentation
~~~~~~~~~~~~~
`Pseud on Readthedocs <https://pseud.readthedocs.io/en/latest/index.html>`_
