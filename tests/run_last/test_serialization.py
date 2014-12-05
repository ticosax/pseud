import datetime

from dateutil.tz import tzlocal
import pytest


def test_datetime_without_timezone():
    from pseud.packer import Packer

    date = datetime.datetime(2003, 9, 27, 9, 40, 1, 521290)
    assert Packer().unpackb(Packer().packb(date)) == date


def test_datetime_with_timezone():
    from pseud.packer import Packer

    date = datetime.datetime(2003, 9, 27, 9, 40, 1, 521290,
                             tzinfo=tzlocal())
    assert Packer().unpackb(Packer().packb(date)) == date


def test_packer_normal():
    from pseud.packer import Packer
    packer = Packer()
    assert packer.unpackb(packer.packb('data')) == 'data'


def test_packer_failure():
    import msgpack
    from pseud.packer import Packer
    packer = Packer()
    with pytest.raises(msgpack.ExtraData):
        packer.unpackb(b'--')


def test_packer_translation():
    import msgpack
    from pseud.packer import Packer

    class A(object):
        def __init__(self, arg):
            self.arg = arg

        def __eq__(self, other):
            return self.arg == other.arg

    table = {5: (A,
                 lambda obj: msgpack.packb(obj.arg),
                 lambda data: A(msgpack.unpackb(data)))}
    packer = Packer(translation_table=table)
    assert packer.packb({b'key': A(b'--')}) == (
        b'\x81\xc4\x03key\xc7\x03\x05\xa2--')
    assert packer.unpackb(
        packer.packb({'key': A(b'arg')})) == {'key': A(b'arg')}

    packer.register_ext_handler(
        0, A, lambda obj: b'overidden', lambda data: A(b'arbitrary'))
    # Checks pack_cache is valid
    assert packer.unpackb(
        packer.packb({'key': A(b'arg')})) != {'key': A(b'arg')}

    # Mostly for coverage of error paths.
    class B(object):
        pass

    # Two different error paths.
    with pytest.raises(TypeError):
        packer.packb(B())
    with pytest.raises(TypeError):
        packer.packb(B())

    dumb_packer = Packer()
    dumb_packer.unpackb(packer.packb(A('')))
