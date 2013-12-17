import os
try:
    from ._tornado import Client, Server
    if os.getenv('NO_TORNADO'):
        raise ImportError
except ImportError:
    from ._gevent import Client, Server  # NOQA
