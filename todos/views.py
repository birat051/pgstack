from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from accounts import services as accounts_services
from todos import forms, services
class IndexView(View):
    """List recent todos on GET; create on POST when authenticated."""

    def get(self, request: HttpRequest) -> HttpResponse:
        todo_form = None
        if request.user.is_authenticated:
            todo_form = forms.TodoCreateForm()
        return render(
            request,
            'todos/index.html',
            {
                'todos': services.list_todos_for_user(request.user),
                'todo_form': todo_form,
            },
        )

    @method_decorator(login_required)
    def post(self, request: HttpRequest) -> HttpResponse:
        todo_form = forms.TodoCreateForm(request.POST)
        if todo_form.is_valid():
            services.create_todo(
                owner=request.user,
                title=todo_form.cleaned_data['title'],
                notes=todo_form.cleaned_data['notes'],
            )
            return redirect('index')

        context = {
            'todos': services.list_todos_for_user(request.user),
            'todo_form': todo_form,
        }
        return render(request, 'todos/index.html', context)


def search(request: HttpRequest) -> HttpResponse:
    q = request.GET.get('q', '')
    todos = services.search_todos(q, user=request.user)
    return render(
        request,
        'todos/search_results.html',
        {'todos': todos, 'q': q},
    )


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    username = (request.GET.get('username') or '').strip()
    todo_list_owner: User | None = None
    if username:
        target = User.objects.filter(username__iexact=username).first()
        if target is None or not accounts_services.can_view_todo_list(request.user, target):
            raise Http404('Todo list unavailable.')
        todo_list_owner = target

    counts = services.dashboard_counts_for_viewer(
        request.user,
        todo_list_owner=todo_list_owner,
    )
    return render(
        request,
        'todos/dashboard.html',
        {
            'counts': counts,
            'view_username': todo_list_owner.username if todo_list_owner else None,
        },
    )


@login_required
def queue_monitor(request: HttpRequest) -> HttpResponse:
    jobs = services.list_jobs_for_user(request.user)
    return render(
        request,
        'todos/queue_monitor.html',
        {'jobs': jobs},
    )
