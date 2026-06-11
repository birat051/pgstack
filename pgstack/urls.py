from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from accounts.forms import LoginForm
from accounts.views import logout, signup

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/login/', LoginView.as_view(authentication_form=LoginForm), name='login'),
    path('auth/signup/', signup, name='signup'),
    path('auth/logout/', logout, name='logout'),
    path('auth/', include('django.contrib.auth.urls')),
    path('', include('accounts.urls')),
    path('', include('todos.urls')),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
