pseud
=====
.. image:: https://travis-ci.org/ezeep/pseud.png?branch=master
   :target: https://travis-ci.org/ezeep/pseud

.. image:: https://coveralls.io/repos/ezeep/pseud/badge.png
   :target: https://coveralls.io/r/ezeep/pseud

.. image:: https://pypip.in/v/pseud/badge.png
   :target: https://crate.io/packages/pseud/
   :alt: Latest PyPI version

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
    # Assume tornado IOLoop is running
    from pseud import Server


    server = Server('service')
    server.bind('tcp://127.0.0.1:5555')

    @server.register_rpc
    def hello(name):
        return 'Hello {0}'.format(name)

    server.start()

.. code-block:: python

    # The tornado client
    # Assume tornado IOLoop is running
    from pseud import Client


    client = Client('service')
    client.connect('tcp://127.0.0.1:5555')

    # Assume we are inside a coroutine
    response = yield client.hello('Charly')
    assert response == 'Hello Charly'

.. code-block:: python

    # The gevent client
    from pseud import Client


    client = Client('service')
    client.connect('tcp://127.0.0.1:5555')

    assert client.hello('Charly').get() == 'Hello Charly'


Documentation
~~~~~~~~~~~~~
`Pseud on Readthedocs <http://pseud.readthedocs.org/en/latest/index.html>`_
