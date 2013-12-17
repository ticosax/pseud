pybidirpc
=========

Pythonic bidirectional-rpc API build on top of ØMQ with pluggable
encryption and authentication support.


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
