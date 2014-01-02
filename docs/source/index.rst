.. pseud documentation master file, created by
   sphinx-quickstart on Fri Dec 20 17:34:16 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

pseud a bidirectionnal RPC library ready for the hostile web
############################################################

Initialize an RPC peer playing as server

.. code-block:: python

   # The server
   from pseud import Server


   server = Server('service')
   server.bind('tcp://127.0.0.1:5555')

   @server.register_rpc
   def hello(name):
       return 'Hello {0}'.format(name)

   server.start() # this would block within its own io_loop

Prepare one client

.. code-block:: python

   # The tornado client
   # Assume tornado IOLoop is running
   from pseud import Client


   client = Client('service')
   client.connect('tcp://127.0.0.1:5555')

then invoke a rpc call

.. code-block:: python

   # Assume we are inside a coroutine
   future = yield client.hello('Charly')
   future.result()  # 'Hello Charly'

Also gevent api for client

.. code-block:: python

   # The gevent client
   from pseud import Client


   client = Client('service')
   client.connect('tcp://127.0.0.1:5555')

   client.hello('Charly').get()  # 'Hello Charly'

Narrative Documentation
=======================

.. toctree::
   :maxdepth: 2

   intro
   remote-calls
   authentication
   heartbeating
   job-routing
   protocol
   interfaces
   changelog

API Documentation
=================

.. toctree::
   :maxdepth: 1
   :glob:

   api/*


Indices and tables
==================

* :ref:`glossary`
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. toctree::
   :hidden:

   glossary
