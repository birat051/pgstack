from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from todos import services


def search(request: HttpRequest) -> HttpResponse:
    q = request.GET.get('q', '')
    todos = services.search_todos(q)
    return render(
        request,
        'todos/search_results.html',
        {'todos': todos, 'q': q},
    )
