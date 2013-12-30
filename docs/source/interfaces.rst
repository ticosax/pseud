.. _interfaces_module:

:mod:`pseud.interfaces`
-----------------------
.. automodule:: pseud.interfaces


RPC-Related Interfaces
++++++++++++++++++++++

.. autointerface:: pseud.interfaces.IBaseRPC
   :members:
.. autointerface:: pseud.interfaces.IServer
   :members:
.. autointerface:: pseud.interfaces.IClient
   :members:

Plugins-Related Interfaces
++++++++++++++++++++++++++

.. autointerface:: pseud.interfaces.IAuthenticationBackend
   :members:
.. autointerface:: pseud.interfaces.IHeartbeatBackend
   :members:
.. autointerface:: pseud.interfaces.IPredicate
   :members:

Constants
+++++++++

:py:const:`WORK`

:py:const:`OK`

:py:const:`ERROR`

:py:const:`HELLO`

:py:const:`UNAUTHORIZED`

:py:const:`AUTHENTICATED`

:py:const:`HEARTBEAT`

Exceptions
++++++++++

.. autoexception:: pseud.interfaces.ServiceNotFoundError
.. autoexception:: pseud.interfaces.TimeoutError
.. autoexception:: pseud.interfaces.UnauthorizedError
