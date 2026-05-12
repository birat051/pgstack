from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from todos import services


def index(request: HttpRequest) -> HttpResponse:
    todos = services.list_recent_todos()
    return render(
        request,
        'todos/index.html',
        {'todos': todos},
    )


def search(request: HttpRequest) -> HttpResponse:
    q = request.GET.get('q', '')
    todos = services.search_todos(q)
    return render(
        request,
        'todos/search_results.html',
        {'todos': todos, 'q': q},
    )
