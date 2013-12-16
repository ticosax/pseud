import textwrap


_marker = object()


def format_remote_traceback(traceback):
    pivot = '\n{}'.format(3 * 4 * ' ')  # like three tabs
    return textwrap.dedent("""
        -- Beginning of remote traceback --
            {}
        -- End of remote traceback --
        """.format(pivot.join(traceback.splitlines())))


class AttributeWrapper(object):
    def __init__(self, rpc, name):
        self.rpc = rpc
        self._part_names = name.split('.')

    def __getattr__(self, name, default=_marker):
        try:
            if default is _marker:
                return super(AttributeWrapper, self).__getattr__(name)
            return super(AttributeWrapper, self).__getattr__(name,
                                                             default=default)
        except AttributeError:
            self.name = name
            return self

    def name_getter(self):
        return '.'.join(self._part_names)

    def name_setter(self, value):
        self._part_names.append(value)

    name = property(name_getter, name_setter)

    def __call__(self, *args, **kw):
        return self.rpc.send_work(self.rpc.peer_identity, self.name,
                                  *args, **kw)
