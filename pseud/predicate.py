import zope.component

from pseud.interfaces import IPredicate, IRPCCallable
from pseud.utils import register_predicate


@register_predicate
@zope.interface.implementer(IPredicate)
@zope.component.adapter(IRPCCallable)
class PassThrough(object):
    """
    Default predicate associated with the `default` :term:`domain`.

    Allows all job to be executed.
    """
    name = 'default'

    def __init__(self, rpc_call):
        self.rpc_call = rpc_call

    def test(self, *args, **kw):
        return True


@register_predicate
@zope.interface.implementer(IPredicate)
@zope.component.adapter(IRPCCallable)
class FilterByModule(object):
    name = 'restricted'

    def __init__(self, rpc_call):
        self.rpc_call = rpc_call

    def test(self, user=None, *args, **kw):
        if user is None:
            return False
        return user.has_permission('DoSomethingNasty')
