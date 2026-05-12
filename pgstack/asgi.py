import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

import todos.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgstack.settings.dev')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': URLRouter(todos.routing.websocket_urlpatterns),
    }
)
