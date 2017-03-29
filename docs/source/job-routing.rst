Job Routing
===========

Predicates
++++++++++

During registration, user can associate a domain to the callable.
Each domain will be linked to a specific Predicate with its own Policy.
By default all rpc-callable are registered within `default` domain, that allow
all callable to be called.
In case of rejection, :mod:`pseud.interfaces.ServiceNotFoundError` exception
will be raised.

You can of course define your own predicate and register some callable under
restricted domain for instance.

.. code:: python

   @register_rpc(name='try_to_call_me')
   def callme(*args, **kw):
       return 'small power'

   @register_rpc(name='try_to_call_me',
                 domain='restricted')
   def callme_admin(*args, **kw):
       return 'great power'

In this example we have 2 callable registered with same name but with
different domain.
Assuming we a have a Authentication Backend that is able to return a user
instance and from this user instance we can know if he is admin.
then we can assume the following behaviour ::

    # anonymous user

    await client.try_to_callme() == 'small power'

Then with user with admin rights ::

    # user admin

    await client.try_to_callme() == 'great power'

From this behaviour we can perform routing based on user permissions.
