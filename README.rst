pseud
=====
.. image:: https://travis-ci.org/ezeep/pseud.svg?branch=master
   :target: https://travis-ci.org/ezeep/pseud

.. image:: https://coveralls.io/repos/ezeep/pseud/badge.png
   :target: https://coveralls.io/r/ezeep/pseud

.. image:: https://pypip.in/version/pseud/badge.svg
   :target: https://pypi.python.org/pypi/pseud/
   :alt: Latest Version

.. image:: https://landscape.io/github/ezeep/pseud/master/landscape.png
   :target: https://landscape.io/github/ezeep/pseud/master
   :alt: Code Health

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
#. Works with tornado ioloop or gevent.
#. Built-in proxy support. A server can delegate the work to another one.
#. SyncClient (using zmq.REQ) to use within non event based processes.
   (Heartbeating, Authentication and job execution are not supported with
   the SyncClient.)

Installation
~~~~~~~~~~~~

Dependencies are declared in setup.py and all automatically installed, but,
pyzmq might build libzmq from bundled folder `OR` from your system wide libzmq.
In later case you should make sure libzmq has been compiled with libsodium
to take advantage of curve security features.

We recommend to install pyzmq with bundled libzmq explicitely if libzmq is
already installed on your system.

.. code-block:: console

   $ pip install pyzmq --install-option='--zmq=bundled'

Tornado
-------

.. code-block:: console

   $ pip install -e .[Tornado]

Gevent
------

.. code-block:: console

   $ pip install -e .[Gevent]


Execution
~~~~~~~~~

If both backends are installed, tornado is used by default.
To force gevent over tornado, set the environment variable `$NO_TORNADO` to
something.

.. code-block:: console

   $ NO_TORNADO=1 python script.py

Preview
~~~~~~~

The tornado Server
------------------

.. code-block:: python

    from pseud import Server


    server = Server('service')
    server.bind('tcp://127.0.0.1:5555')

    @server.register_rpc
    def hello(name):
        return 'Hello {0}'.format(name)

    server.start()  # this will block forever


The tornado Client
------------------

.. code-block:: python

    # Assume the tornado IOLoop is running
    from pseud import Client


    client = Client('service', identity='client1', io_loop=loop)
    client.connect('tcp://127.0.0.1:5555')

    # Assume we are inside a coroutine
    response = yield client.hello('Charly')
    assert response == 'Hello Charly'

    @client.register_rpc(name='draw.me.a.sheep')
    def sheep():
        return 'beeeh'


The gevent Client
-----------------

.. code-block:: python

    from pseud import Client


    client = Client('service')
    client.connect('tcp://127.0.0.1:5555')

    assert client.hello('Charly').get() == 'Hello Charly'

The SyncClient
--------------

.. code-block:: python

   # to use within a non-asynchronous process or in a command interpreter
   from pseud import SyncClient


   client = SyncClient()
   client.connect('tcp://127.0.0.1:5555')

   assert client.hello('Charly') == 'Hello Charly'



The Server send a command to the client
---------------------------------------

.. code-block:: python

   # assume we are inside a coroutine
   sheep = yield server.send_to('client1').draw.me.a.sheep()
   assert sheep == 'beeeh'



Documentation
~~~~~~~~~~~~~
`Pseud on Readthedocs <http://pseud.readthedocs.org/en/latest/index.html>`_
