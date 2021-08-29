import logging

import zmq
import zope.interface

from .common import BaseRPC
from .interfaces import (
    IServer,
)


logger = logging.getLogger(__name__)


@zope.interface.implementer(IServer)
class Server(BaseRPC):
    socket_type = zmq.ROUTER

    def __init__(self, user_id, routing_id=None, **kw):
        if routing_id:
            raise TypeError('routing_id argument is prohibited')
        super(Server, self).__init__(user_id=user_id, routing_id=user_id, **kw)
