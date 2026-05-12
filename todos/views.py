from django.http import HttpRequest, HttpResponse


def placeholder(_request: HttpRequest) -> HttpResponse:
    return HttpResponse('todos')
