"""End-to-end navigation flow across all wired pages (PR 16)."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.models import UserSettings


_PASSWORD = 'n0OrdinaryHorseBatteryStaple!x'

_NAV_PATHS_AUTHENTICATED = (
    '/',
    '/search/',
    '/users/search/',
    '/dashboard/',
    '/queue/',
    '/settings/',
)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class FullAppNavigationTests(TestCase):
    """Simulate signup → nav every page → create todo → logout in one session."""

    def _assert_global_nav(self, response, *, authenticated: bool) -> None:
        self.assertContains(response, 'href="/"')
        self.assertContains(response, 'href="/search/"')
        self.assertContains(response, 'href="/users/search/"')
        self.assertContains(response, 'href="/dashboard/"')
        self.assertContains(response, 'href="/queue/"')
        self.assertContains(response, 'href="/settings/"')
        if authenticated:
            self.assertContains(response, 'Log out')
            self.assertNotContains(response, 'href="/auth/signup/"')
        else:
            self.assertContains(response, 'href="/auth/login/"')
            self.assertContains(response, 'href="/auth/signup/"')

    def test_full_app_navigation_end_to_end(self) -> None:
        # Anonymous: public pages load with logged-out nav.
        landing = self.client.get('/')
        self.assertEqual(landing.status_code, 200)
        self._assert_global_nav(landing, authenticated=False)

        for path in ('/search/', '/auth/login/', '/auth/signup/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=path)
            self._assert_global_nav(response, authenticated=False)

        for path in ('/dashboard/', '/queue/', '/users/search/', '/settings/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, msg=path)
            self.assertIn('/auth/login/', response.url)

        # Sign up and land on home (session established).
        signup = self.client.post(
            '/auth/signup/',
            {
                'name': 'Nav Walker',
                'email': 'nav.walker@example.com',
                'password': _PASSWORD,
                'password_confirm': _PASSWORD,
            },
            follow=True,
        )
        self.assertEqual(signup.status_code, 200)
        self.assertContains(signup, 'Todos')
        self._assert_global_nav(signup, authenticated=True)

        user = get_user_model().objects.get(email__iexact='nav.walker@example.com')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

        # Walk every nav destination while authenticated.
        for path in _NAV_PATHS_AUTHENTICATED:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=path)
            self._assert_global_nav(response, authenticated=True)

        # Create a todo from home, then verify downstream pages reflect it.
        created = self.client.post(
            '/',
            {'title': 'Navigation demo todo', 'notes': 'postgres notify fts queue'},
            follow=True,
        )
        self.assertEqual(created.status_code, 200)
        self.assertContains(created, 'Navigation demo todo')

        search = self.client.get('/search/', {'q': 'Navigation'})
        self.assertEqual(search.status_code, 200)
        self.assertContains(search, 'Navigation demo todo')

        dashboard = self.client.get('/dashboard/')
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, 'Todo counts by status')
        self.assertContains(dashboard, 'Pending')

        queue = self.client.get('/queue/')
        self.assertEqual(queue.status_code, 200)
        self.assertContains(queue, 'Navigation demo todo')
        self.assertContains(queue, 'send_reminder')

        settings_save = self.client.post(
            '/settings/',
            {'is_todo_list_private': 'on'},
            follow=True,
        )
        self.assertEqual(settings_save.status_code, 200)
        self.assertContains(settings_save, 'Todo list visibility updated.')
        self.assertTrue(
            UserSettings.objects.get(user=user).is_todo_list_private,
        )

        user_search = self.client.get('/users/search/', {'q': user.username[:4]})
        self.assertEqual(user_search.status_code, 200)
        self.assertContains(user_search, user.username)

        own_list = self.client.get(f'/users/{user.username}/todos/')
        self.assertEqual(own_list.status_code, 200)
        self.assertContains(own_list, 'Navigation demo todo')

        # Log out; protected routes redirect again.
        logged_out = self.client.post('/auth/logout/', follow=True)
        self.assertEqual(logged_out.status_code, 200)
        self._assert_global_nav(logged_out, authenticated=False)
        self.assertNotIn('_auth_user_id', self.client.session)

        for path in ('/dashboard/', '/queue/', '/users/search/', '/settings/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, msg=path)
            self.assertIn('/auth/login/', response.url)
