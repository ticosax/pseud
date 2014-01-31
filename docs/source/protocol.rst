.. _protocol:

Protocol v1
===========

pseud uses to transport its messages ØMQ with ROUTER sockets.
the structure of every frames follow this specification.

ENVELOPE + PSEUD MESSAGE

ENVELOPE
++++++++

The envelope belongs to ømq typology to route messages to right recipient.
the are separated from pseud message with empty delimiter ``''``.
Basically the envelope will be ::

    ['peer_identity', '']


PSEUD MESSAGE
+++++++++++++
FRAME 0: :term:`VERSION` of current protocol ::

    utf-8 string 'v1'

FRAME 1: message uuid ::

    bytes uuid4 or empty string for hearbeat messages

FRAME 2: message type ::

    byte

FRAME 3: body ::

    WORK, OK, ERROR and HELLO expect msgpack.
    AUTHENTICATED, UNAUTHORIZED and HEARTBEAT expect utf-8 strings.


MESSAGE TYPES
+++++++++++++

WORK
~~~~

.. code::

    '\x03'

the body content is a tuple of 3 items
    #. dotted name of the rpc-callable
    #. tuple of positional arguments
    #. dict of keyword arguments

OK
~~

.. code::

   '\x01'

ERROR
~~~~~

.. code::

    '\x10'

the body content is a tuple of 3 items
    #. string of Exception class name e.g. 'AttributeError'
    #. message of the exception
    #. Remote traceback

UNAUTHORIZED
~~~~~~~~~~~~

.. code::

    '\x11'

HELLO
~~~~~

.. code::

    '\x02'

the body content is a tuple of 2 items
    #. login
    #. password

AUTHENTICATED
~~~~~~~~~~~~~

.. code::

    '\x04'

HEARTBEAT
~~~~~~~~~

.. code::

    '\x06'

COMMUNICATION
+++++++++++++

#. client sends work to server and receive successful answer.

    +--------+------+----+--------+
    | client |  ->  | <- | server |
    +--------+------+----+--------+
    |        | WORK |    |        |
    +--------+------+----+--------+
    |        |      | OK |        |
    +--------+------+----+--------+

#. client sends work to server and receive an error.

    +--------+------+-------+--------+
    | client |  ->  |  <-   | server |
    +--------+------+-------+--------+
    |        | WORK |       |        |
    +--------+------+-------+--------+
    |        |      | ERROR |        |
    +--------+------+-------+--------+

#. server sends work to client and receive successful answer.

    +--------+-----+------+--------+
    | client |  -> | <-   | server |
    +--------+-----+------+--------+
    |        |     | WORK |        |
    +--------+-----+------+--------+
    |        | OK  |      |        |
    +--------+-----+------+--------+

#. client sends an heartbeat

    +--------+-----------+-----+--------+
    | client |    ->     |  <- | server |
    +--------+-----------+-----+--------+
    |        | HEARTBEAT |     |        |
    +--------+-----------+-----+--------+

#. server sends an heartbeat

    +--------+-----+-------------+--------+
    | client |  -> |      <-     | server |
    +--------+-----+-------------+--------+
    |        |     |   HEARTBEAT |        |
    +--------+-----+-------------+--------+

#. client send a job and server requires authentication

    +--------+-------+-----------------+--------+
    | client |  ->   |       <-        | server |
    +--------+-------+-----------------+--------+
    |        | WORK  |                 |        |
    +--------+-------+-----------------+--------+
    |        |       |  UNAUTHORIZED   |        |
    +--------+-------+-----------------+--------+
    |        | HELLO |                 |        |
    +--------+-------+-----------------+--------+
    |        |       |  AUTHENTICATED  |        |
    +--------+-------+-----------------+--------+
    |        | WORK  |                 |        |
    +--------+-------+-----------------+--------+
    |        |       |       OK        |        |
    +--------+-------+-----------------+--------+

#. client send a job and server requires authentication but fails

    +--------+-------+---------------+--------+
    | client |  ->   |       <-      | server |
    +--------+-------+---------------+--------+
    |        | WORK  |               |        |
    +--------+-------+---------------+--------+
    |        |       |  UNAUTHORIZED |        |
    +--------+-------+---------------+--------+
    |        | HELLO |               |        |
    +--------+-------+---------------+--------+
    |        |       |  UNAUTHORIZED |        |
    +--------+-------+---------------+--------+
