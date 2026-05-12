from django.urls import path

from accounts import views

urlpatterns = [
    path('settings/', views.user_settings, name='settings'),
]
