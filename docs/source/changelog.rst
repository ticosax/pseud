Changelog history
=================


1.0.1dev - Not yet released
---------------------------

1.0.0 - 2018/04/17
------------------
  - enable PROBING
  - Switch to pipenv
  - maintenance of dependencies + tests cleanup

1.0.0-a1 - 2017/04/09
--------------------

Features
________

    - Add reliable authentication (thx to zmq_msg_gets())
      We can now reliably know who is sending messages, this feature is required
      with an authentication backend that use the zap handler.
      Just PLAIN, and CURVE can do the job.
    - Add support for async context manager interface:
    - rely on PROBE_ROUTER socket option to let clients register themselves (instead of relying on heartbeat backend).

.. code-block:: python

    async with server:
        # do something
        ...
    # socket is closed


Breaking Changes
----------------
    - Only python3.6+ is supported
    - Only asyncio is supported (tornado and gevent are dropped)

.. note::

   This break backward compatibility.
   Interfaces are renewed and internal API is modified.
   It is not longer possible to hardcode socket's routing_id for clients.

.. note::

    pseud requires at least pyzmq 14.4.0 + libzmq-4.1.0 with ``zmq_msg_gets()``

Bug Fixes
_________

    - RPCCallable from local registry receive better priority if two registered RPCs share the same name.

0.0.5 - 2014/08/27
------------------

    - Add python3.4 support for Tornado backend

0.0.4 - 2014/03/25
------------------

0.0.3 - 2014/02/24
------------------

  - Add support of Aysnc RPC callables for Tornado
  - Add support of datetime (tz aware) serializations by msgpack

0.0.2 - 2014/02/13
------------------

0.0.1 - 2014/01/27
------------------

- Scaffolding of the lib
