pseud
=====
.. image:: https://travis-ci.org/ticosax/pseud.svg?branch=master
   :target: https://travis-ci.org/ticosax/pseud

.. image:: https://codecov.io/gh/ticosax/pseud/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/ticosax/pseud

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

libzmq 4.1 is now required. As it is not yet bundled within pyzmq you will
need to compile it yourself.
Also `libsodium <https://github.com/jedisct1/libsodium>`_ is a required
dependency of pseud.

For ubuntu distribution, a ppa exists.

.. code-block:: console

   $ sudo add-apt-repository -y ppa:shnatsel/dnscrypt
   $ sudo apt-get update -q && sudo apt-get install -y libsodium-dev


.. code-block:: console

   $ curl https://github.com/zeromq/zeromq4-1/archive/master.zip -L > zeromq4-1.zip
   $ sh -c 'unzip zeromq4-1.zip; cd zeromq4-1; sh autogen.sh; ./configure --with-libsodium; make -j; sudo make install; sudo ldconfig'


Then you can install latest pyzmq from pypi

.. code-block:: console

   $ pip install pyzmq --install-option="--zmq=/usr/local"


Choose your backend
~~~~~~~~~~~~~~~~~~~

Pseud can be used with either tornado or gevent.
As they can not be used both as the same time, you need to decide
which one you want to use on installation time.

Tornado
-------

.. code-block:: console

   $ pip install "pseud[Tornado]"

Gevent
------

.. code-block:: console

   $ pip install "pseud[Gevent]"


Execution
~~~~~~~~~

If both backends are installed (like in developer environment),
tornado is used by default.
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


    client = Client('service', io_loop=loop)
    client.connect('tcp://127.0.0.1:5555')

    # Assume we are inside a coroutine
    response = yield client.hello('Charly')
    assert response == 'Hello Charly'



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

   server.start()  # this will block forever

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
   result = yield client.hello('alice')
   assert result == 'Hello alice'

Back on server side, now the client as registered itself, we can send
to it any commands the client is able to do.

.. code-block:: python

    # assume we are inside a coroutine
    sheep = yield server.send_to('alice').draw.me.a.sheep()
    assert sheep == 'beeeh'


Documentation
~~~~~~~~~~~~~
`Pseud on Readthedocs <http://pseud.readthedocs.org/en/latest/index.html>`_
