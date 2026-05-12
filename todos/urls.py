from django.urls import path

from todos import views

urlpatterns = [
    path('search/', views.search, name='search'),
]
