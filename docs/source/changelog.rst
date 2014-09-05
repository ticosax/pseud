Changelog history
=================

0.1.0 - Not Yet Released
------------------------

Features
________

    - Add reliable authentication (thx to zmq_msg_gets())
      We can now reliably know who is sending messages, this feature is required
      with an authentication backend that use the zap handler.
      Just PLAIN, and CURVE are can do the job.

.. note::

   This break backward compatibility.
   Interfaces are renewed and internal API is modified.
   It is not longer possible to hardcode socket's routing_id for clients.

.. note::

    pseud requires pyzmq 14.4.0 + libzmq-4.1.0 with ``zmq_msg_gets()``

Bug Fixes
_________

    - Tornado 4 is supported

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
