from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts import services as accounts_services
from accounts.forms import SignupForm
from todos import services as todos_services


@login_required
def user_search(request: HttpRequest) -> HttpResponse:
    q = request.GET.get('q', '')
    users = accounts_services.search_users_by_username(q)
    return render(
        request,
        'accounts/user_search.html',
        {'users': users, 'q': q},
    )


@login_required
def user_todo_list(request: HttpRequest, username: str) -> HttpResponse:
    owner = User.objects.filter(username__iexact=username).first()
    if owner is None or not accounts_services.can_view_todo_list(request.user, owner):
        raise Http404('Todo list unavailable.')
    q = request.GET.get('q', '')
    if q.strip():
        todos = todos_services.search_todos(q, user=request.user, list_owner=owner)
    else:
        todos = todos_services.list_todos_for_owner(owner)
    return render(
        request,
        'accounts/user_todo_list.html',
        {
            'owner': owner,
            'todos': todos,
            'is_own_list': request.user.pk == owner.pk,
            'q': q,
        },
    )


@login_required
def user_settings(request: HttpRequest) -> HttpResponse:
    settings_row = accounts_services.get_or_create_user_settings(request.user)
    if request.method == 'POST':
        is_private = request.POST.get('is_todo_list_private') == 'on'
        accounts_services.set_todo_list_privacy(request.user, is_private)
        messages.success(request, 'Todo list visibility updated.')
        return redirect('settings')
    return render(
        request,
        'accounts/user_settings.html',
        {'is_todo_list_private': settings_row.is_todo_list_private},
    )


def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('index')
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = accounts_services.register_user(
                display_name=form.cleaned_data['name'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
            )
            auth_login(request, user)
            messages.success(request, 'Account created. You are now logged in.')
            return redirect('index')
    else:
        form = SignupForm()
    return render(request, 'accounts/signup.html', {'form': form})


@require_http_methods(['GET', 'HEAD', 'POST'])
def logout(request: HttpRequest) -> HttpResponse:
    """Log out when authenticated (GET or POST) and redirect to the login page."""
    if request.user.is_authenticated:
        auth_logout(request)
    return redirect(reverse('login'))
