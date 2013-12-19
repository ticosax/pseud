import zope.component

from pybidirpc.interfaces import IPredicate, IRPCCallable
from pybidirpc.utils import register_predicate


@register_predicate
@zope.interface.implementer(IPredicate)
@zope.component.adapter(IRPCCallable)
class PassThrough(object):
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
