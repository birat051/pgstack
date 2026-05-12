from django.contrib import admin
from django.urls import include, path

from accounts.views import logout, signup

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/signup/', signup, name='signup'),
    path('auth/logout/', logout, name='logout'),
    path('auth/', include('django.contrib.auth.urls')),
    path('', include('accounts.urls')),
    path('', include('todos.urls')),
]
