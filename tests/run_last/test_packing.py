
def test_packer_normal():
    from pseud.packer import Packer
    packer = Packer()
    assert packer.unpackb(packer.packb('data')) == 'data'


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
    assert (
        packer.packb({'key': A('--')}) == '\x81\xc4\x03key\xc7\x03\x05\xa2--')
    assert packer.unpackb(packer.packb({'key': A('arg')})) == {'key': A('arg')}
