Introduction
============

It already exists several RPC Libraries for python. Very mature tested with a
community behind. So why build yet another one ?

We discover that most of those libraries make the assumption that they are running
within a trusted network; that a client/server architecture means clients connect and consume
resources exposed by the server and not vice versa.

With `pseud` we want to overcome RESTful api with RPC style communication. With small
applications communicating back and forth within an hostile network. RESTful is
nice for the browser, but become an impediment when used to allow
communication for machine to machine.

There is no real technical challenge behind this library, most of the key
features are provided out of the box by the amazing `ØMQ <http://zeromq.org/>`_ library and
`pyzmq <https://github.com/zeromq/pyzmq>`_ .

`pseud` just provide a convenient and pythonic API to hide some complexity and
boiler plate code to the developer. It should be fun to code with.

Also thanks to the `ZCA <http://docs.zope.org/zope.component/>`_, `pseud` comes with a pluggable architecture that allows
easy integration within your existing stack. It is usable within any web application (Django, Pyramid, Tornado, ...).

pseud also comes with gevent event loop and the Tornado event loop, just choose your favorite weapon.
