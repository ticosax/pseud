try:
    from ._tornado import Client, Server
except ImportError:
    from ._gevent import Client, Server  # NOQA
