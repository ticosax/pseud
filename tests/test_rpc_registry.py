import functools

import pytest
from zope.interface.registry import Components


def test_rpc_simple_registration():
    from pseud.interfaces import ServiceNotFoundError
    from pseud.utils import RPCCallable, get_rpc_callable, register_rpc

    @register_rpc
    def callme(*args, **kw):
        return args, kw

    assert isinstance(get_rpc_callable('callme'), RPCCallable)
    assert get_rpc_callable('callme')() == ((), {})
    assert get_rpc_callable('callme')('a', foo='goo') == (('a',), {'foo': 'goo'})

    @register_rpc(name='totally.something.else')
    def callme2(*args, **kw):
        return args, kw

    with pytest.raises(ServiceNotFoundError):
        get_rpc_callable('callme2')

    assert isinstance(get_rpc_callable('totally.something.else'), RPCCallable)

    def call_me_again():
        return True

    register_rpc(functools.partial(call_me_again), name='call_me_again')
    assert get_rpc_callable('call_me_again')() is True


def test_rpc_restricted_registration():
    from pseud.interfaces import ServiceNotFoundError
    from pseud.utils import get_rpc_callable, register_rpc

    @register_rpc(name='try_to_call_me')
    def callme(*args, **kw):
        return 'small power'

    @register_rpc(name='try_to_call_me', domain='restricted')
    def callme_admin(*args, **kw):
        return 'great power'

    @register_rpc(name='on.admin.can.call.me', domain='restricted')
    def callme_admin2(*args, **kw):
        return 'great power'

    class User:
        def __init__(self, allowed):
            self.allowed = allowed

        def has_permission(self, perm):
            return self.allowed

    guest = User(False)
    admin = User(True)

    assert get_rpc_callable('try_to_call_me', user=guest)() == 'small power'

    assert get_rpc_callable('try_to_call_me', user=admin)() == 'great power'

    with pytest.raises(ServiceNotFoundError):
        get_rpc_callable('on.admin.can.call.me', user=guest)

    assert get_rpc_callable('on.admin.can.call.me', user=admin)() == 'great power'


def test_registration_with_custom_registry():
    from pseud.utils import get_rpc_callable, register_rpc, registry

    local_registry = Components(name='local', bases=(registry,))

    @register_rpc(name='try_to_call_me')
    def callme(*args, **kw):
        return 'global'

    @register_rpc(name='try_to_call_me', registry=local_registry)
    def callme2(*args, **kw):
        return 'local'

    assert get_rpc_callable('try_to_call_me')() == 'global'
    assert get_rpc_callable('try_to_call_me', registry=local_registry)() == 'local'
