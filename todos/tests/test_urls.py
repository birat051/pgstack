"""Verify public app URL wiring (PR 16 — Wire all URLs)."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import resolve, reverse

from accounts.views import signup, user_search, user_settings, user_todo_list
from todos.views import IndexView, dashboard, queue_monitor, search


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class UrlWiringTests(TestCase):
    """Named routes, path resolution, and nav pages load."""

    def test_todos_named_routes_reverse(self) -> None:
        self.assertEqual(reverse('index'), '/')
        self.assertEqual(reverse('search'), '/search/')
        self.assertEqual(reverse('dashboard'), '/dashboard/')
        self.assertEqual(reverse('queue_monitor'), '/queue/')

    def test_accounts_named_routes_reverse(self) -> None:
        self.assertEqual(reverse('user_search'), '/users/search/')
        self.assertEqual(
            reverse('user_todos', kwargs={'username': 'alice'}),
            '/users/alice/todos/',
        )
        self.assertEqual(reverse('settings'), '/settings/')

    def test_auth_named_routes_reverse(self) -> None:
        self.assertEqual(reverse('signup'), '/auth/signup/')
        self.assertEqual(reverse('logout'), '/auth/logout/')
        self.assertEqual(reverse('login'), '/auth/login/')

    def test_todos_routes_resolve_to_views(self) -> None:
        self.assertEqual(resolve('/').func.view_class, IndexView)
        self.assertEqual(resolve('/search/').func, search)
        self.assertEqual(resolve('/dashboard/').func, dashboard)
        self.assertEqual(resolve('/queue/').func, queue_monitor)

    def test_accounts_routes_resolve_to_views(self) -> None:
        self.assertEqual(resolve('/users/search/').func, user_search)
        match = resolve('/users/bob/todos/')
        self.assertEqual(match.func, user_todo_list)
        self.assertEqual(match.kwargs['username'], 'bob')
        self.assertEqual(resolve('/settings/').func, user_settings)

    def test_signup_route_resolves(self) -> None:
        self.assertEqual(resolve('/auth/signup/').func, signup)

    def test_anonymous_public_pages_return_ok(self) -> None:
        for path in ('/', '/search/', '/auth/login/', '/auth/signup/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=path)

    def test_login_required_routes_redirect_anonymous(self) -> None:
        for path in (
            '/dashboard/',
            '/queue/',
            '/users/search/',
            '/settings/',
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, msg=path)
            self.assertIn('/auth/login/', response.url)

    def test_authenticated_nav_pages_return_ok(self) -> None:
        user = get_user_model().objects.create_user(
            username='nav_user',
            password='testpass123!',
            email='nav@example.com',
        )
        self.client.login(username='nav_user', password='testpass123!')
        for path in (
            '/',
            '/search/',
            '/dashboard/',
            '/queue/',
            '/users/search/',
            '/settings/',
            f'/users/{user.username}/todos/',
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=path)

    def test_base_nav_links_render_on_index(self) -> None:
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        for href in (
            'href="/"',
            'href="/search/"',
            'href="/users/search/"',
            'href="/dashboard/"',
            'href="/queue/"',
            'href="/settings/"',
            'href="/auth/login/"',
            'href="/auth/signup/"',
        ):
            self.assertContains(response, href)
