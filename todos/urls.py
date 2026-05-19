from django.urls import path

from todos import views

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('search/', views.search, name='search'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('queue/', views.queue_monitor, name='queue_monitor'),
]
