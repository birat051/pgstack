from django.urls import path

from accounts import views

urlpatterns = [
    path('users/search/', views.user_search, name='user_search'),
    path(
        'users/<str:username>/todos/',
        views.user_todo_list,
        name='user_todos',
    ),
    path('settings/', views.user_settings, name='settings'),
]
