Introduction
============

There are already plenty RPC libraries for Python. Many of them mature, tested and with an 
active community behind. So why build yet another one?

We discovered that most of those libraries make the assumption that they're running
within a trusted network; that a client/server architecture means clients connect and consume
resources exposed by the server and not vice versa.

RESTful APIs are great to consume them in the browser or in a simple client/server architecture.
Once you add more distributed components and services to the game, running on potentially hostile 
networks, the common HTTP/RESTful design pattern becomes less practical. With `pseud` we can get
over these limitations by providing secure, fault-tolerant, RPC style communication built for
fast and easy machine to machine communication.

`pseud` is based on the amazing `ØMQ <http://zeromq.org/>`_ library and `pyzmq <https://github.com/zeromq/pyzmq>`_ .
It provides a convenient and pythonic API to hide some of the library's complexity and provides 
boilerplate code to save your time and headaches.

Also thanks to the `ZCA <http://docs.zope.org/zope.component/>`_, `pseud` comes with a pluggable architecture that allows
easy integration within your existing stack. It is usable within any web application (Django, Pyramid, Tornado, ...).

pseud also comes with gevent event loop and the Tornado event loop, just choose your favorite weapon.
