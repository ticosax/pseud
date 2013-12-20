pseud
=====

Pythonic bidirectional-rpc API build on top of ØMQ with pluggable
encryption and authentication support.

Features
~~~~~~~~
#. ØMQ transport layer
#. all native python types supported (msgpack)
#. First citizen exceptions
#. Bi-bidirectional (server can initiate calls to connected clients)
#. Encryption based on CURVE
#. Pluggable Authentication
#. Pluggable Heartbeating
#. Pluggable Job Routing
#. Works with tornado ioloop or gevent 
#. Built-in proxy support. A server can delegate the work to another one.
#. AsyncClient (using zmq.REQ, with limited set of features) to use within non asynchronous process.

Installation
~~~~~~~~~~~~

Tornado
-------

.. code-block:: console

   pip install -e .[Tornado]

Gevent
------

.. code-block:: console

   pip install -e .[Gevent]


Execution
~~~~~~~~~

If both backends are installed, tornado is used by default.
To force gevent over tornado, set the environment variable `$NO_TORNADO` to
something.

.. code-block:: console

        NO_TORNADO=1 python script.py

Preview
~~~~~~~

.. code-block:: python

    # The server
    from pseud import Server


    server = Server('service')

    @server.register_rpc
    def hello(name):
        return 'Hello {0}'.format(name)

    server.start()

.. code-block:: python

    # The tornado client
    from pseud import Client


    client = Client('me', 'service')

    future = yield client.hello('Charly')
    future.result()  # 'Hello Charly'

.. code-block:: python

    # The gevent client
    from pseud import Client


    client = Client('me', 'service')

    client.hello('Charly').get()  # 'Hello Charly'
