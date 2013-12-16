import zope.component
import zope.interface

from .auth import (NoOpAuthenticationBackend,
                   CurveWithTrustedKeyForClient,
                   CurveWithTrustedKeyForServer,
                   CurveWithUntrustedKeyForClient,
                   CurveWithUntrustedKeyForServer,
                   )
from .interfaces import IAuthenticationBackend, IClient, IServer

registry = zope.component.getGlobalSiteManager()

registry.registerAdapter(NoOpAuthenticationBackend, (IClient,),
                         IAuthenticationBackend,
                         NoOpAuthenticationBackend.name)
registry.registerAdapter(NoOpAuthenticationBackend, (IServer,),
                         IAuthenticationBackend,
                         NoOpAuthenticationBackend.name)

registry.registerAdapter(CurveWithTrustedKeyForClient, (IClient,),
                         IAuthenticationBackend,
                         CurveWithTrustedKeyForClient.name)

registry.registerAdapter(CurveWithTrustedKeyForServer, (IServer,),
                         IAuthenticationBackend,
                         CurveWithTrustedKeyForServer.name)

registry.registerAdapter(CurveWithUntrustedKeyForClient, (IClient,),
                         IAuthenticationBackend,
                         CurveWithUntrustedKeyForClient.name)

registry.registerAdapter(CurveWithUntrustedKeyForServer, (IServer,),
                         IAuthenticationBackend,
                         CurveWithUntrustedKeyForClient.name)
