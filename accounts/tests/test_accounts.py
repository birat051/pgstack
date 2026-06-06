import unittest

from django.contrib.auth.models import AnonymousUser, User
from django.db import connection
from django.test import TestCase, override_settings

from accounts import services
from accounts.models import UserSettings
from todos.models import Todo, TodoStatus


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class UserSettingsModelTests(TestCase):
    def test_default_privacy_is_private(self) -> None:
        user = User.objects.create_user(username='u1', password='x')
        row = UserSettings.objects.create(user=user)
        self.assertTrue(row.is_todo_list_private)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class UserSettingsServicesTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(username='owner', password='pw')
        self.other = User.objects.create_user(username='other', password='pw')

    def test_get_or_create_user_settings_creates_with_private_default(self) -> None:
        row = services.get_or_create_user_settings(self.owner)
        self.assertEqual(row.user_id, self.owner.pk)
        self.assertTrue(row.is_todo_list_private)

    def test_owner_can_view_own_list_regardless_of_privacy(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=False)
        self.assertTrue(services.can_view_todo_list(self.owner, self.owner))
        services.set_todo_list_privacy(self.owner, is_private=True)
        self.assertTrue(services.can_view_todo_list(self.owner, self.owner))

    def test_other_user_cannot_view_private_list(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=True)
        self.assertFalse(services.can_view_todo_list(self.other, self.owner))

    def test_anonymous_cannot_view_private_list(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=True)
        self.assertFalse(services.can_view_todo_list(AnonymousUser(), self.owner))

    def test_other_user_can_view_public_list_when_authenticated(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=False)
        self.assertTrue(services.can_view_todo_list(self.other, self.owner))

    def test_anonymous_cannot_view_public_list_of_other_user(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=False)
        self.assertFalse(services.can_view_todo_list(AnonymousUser(), self.owner))


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class UserSearchServicesTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username='alice_public', password='pw')
        User.objects.create_user(username='alice_other', password='pw')
        User.objects.create_user(username='bob', password='pw')

    def test_empty_query_returns_no_users(self) -> None:
        self.assertEqual(list(services.search_users_by_username('')), [])
        self.assertEqual(list(services.search_users_by_username('   ')), [])

    def test_case_insensitive_contains_match(self) -> None:
        usernames = list(
            services.search_users_by_username('ALICE').values_list('username', flat=True)
        )
        self.assertEqual(usernames, ['alice_other', 'alice_public'])

    def test_result_limit(self) -> None:
        for n in range(25):
            User.objects.create_user(username=f'prefix_user_{n:02d}', password='pw')
        usernames = list(
            services.search_users_by_username('prefix_user').values_list('username', flat=True)
        )
        self.assertEqual(len(usernames), 20)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class UserSearchViewTests(TestCase):
    def setUp(self) -> None:
        self.viewer = User.objects.create_user(username='viewer', password='secret')
        User.objects.create_user(username='findme', password='pw')

    def test_user_search_requires_login(self) -> None:
        response = self.client.get('/users/search/', {'q': 'find'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)

    def test_authenticated_search_renders_matches(self) -> None:
        self.client.login(username='viewer', password='secret')
        response = self.client.get('/users/search/', {'q': 'findme'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'findme')
        self.assertContains(response, '/users/findme/todos/')

    def test_authenticated_search_empty_state(self) -> None:
        self.client.login(username='viewer', password='secret')
        response = self.client.get('/users/search/', {'q': 'zzznonexistent'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No users match')
        self.assertContains(response, 'zzznonexistent')

    def test_search_form_uses_get(self) -> None:
        self.client.login(username='viewer', password='secret')
        response = self.client.get('/users/search/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'method="get"')
        self.assertContains(response, 'name="q"')


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class UserTodoListViewTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(username='list_owner', password='pw')
        self.viewer = User.objects.create_user(username='list_viewer', password='secret')
        self.public_todo = Todo.objects.create(
            title='public item',
            owner=self.owner,
            status=TodoStatus.PENDING,
        )
        self.private_todo = Todo.objects.create(
            title='private secret',
            owner=self.owner,
            status=TodoStatus.DONE,
        )

    def test_anonymous_redirects_to_login_before_visibility(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=False)
        response = self.client.get(f'/users/{self.owner.username}/todos/')
        self.assertRedirects(
            response,
            f'/auth/login/?next=/users/{self.owner.username}/todos/',
            fetch_redirect_response=False,
        )

    def test_owner_sees_own_list_when_private(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=True)
        self.client.login(username='list_owner', password='pw')
        response = self.client.get(f'/users/{self.owner.username}/todos/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'public item')
        self.assertContains(response, 'private secret')
        self.assertContains(response, 'Your todos')

    def test_other_user_sees_public_list(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=False)
        self.client.login(username='list_viewer', password='secret')
        response = self.client.get(f'/users/{self.owner.username}/todos/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'public item')
        self.assertContains(response, 'list_owner')

    def test_other_user_gets_404_for_private_list(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=True)
        self.client.login(username='list_viewer', password='secret')
        response = self.client.get(f'/users/{self.owner.username}/todos/')
        self.assertEqual(response.status_code, 404)

    def test_unknown_username_is_404(self) -> None:
        self.client.login(username='list_viewer', password='secret')
        response = self.client.get('/users/no_such_user/todos/')
        self.assertEqual(response.status_code, 404)

    def test_username_lookup_is_case_insensitive(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=False)
        self.client.login(username='list_viewer', password='secret')
        response = self.client.get('/users/LIST_OWNER/todos/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'public item')


@unittest.skipUnless(
    connection.vendor == 'postgresql',
    'Hybrid search uses pg_trgm and SearchVector',
)
@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class UserTodoListSearchTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(username='search_list_owner', password='pw')
        self.viewer = User.objects.create_user(username='search_list_viewer', password='secret')
        Todo.objects.create(
            title='Owner alpha todo',
            notes='unique alpha notes',
            owner=self.owner,
        )
        Todo.objects.create(
            title='Viewer alpha todo',
            notes='viewer alpha notes',
            owner=self.viewer,
        )

    def test_owner_list_search_finds_only_owner_todos(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=False)
        self.client.login(username='search_list_viewer', password='secret')
        response = self.client.get(
            f'/users/{self.owner.username}/todos/',
            {'q': 'alpha'},
        )
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context['todos']]
        self.assertIn('Owner alpha todo', titles)
        self.assertNotIn('Viewer alpha todo', titles)

    def test_private_owner_list_search_is_404_for_other_user(self) -> None:
        services.set_todo_list_privacy(self.owner, is_private=True)
        self.client.login(username='search_list_viewer', password='secret')
        response = self.client.get(
            f'/users/{self.owner.username}/todos/',
            {'q': 'alpha'},
        )
        self.assertEqual(response.status_code, 404)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class Pr09AuthTests(TestCase):
    """PR 09 — user search, public/private lists, owner-scoped todo search."""

    def test_username_search_finds_expected_users_and_limits_noise(self) -> None:
        User.objects.create_user(username='charlie', password='pw')
        User.objects.create_user(username='charlotte', password='pw')
        User.objects.create_user(username='dave', password='pw')
        viewer = User.objects.create_user(username='pr09_viewer', password='secret')
        self.client.login(username='pr09_viewer', password='secret')
        response = self.client.get('/users/search/', {'q': 'charl'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'charlie')
        self.assertContains(response, 'charlotte')
        self.assertNotContains(response, 'dave')

    def test_username_search_does_not_expose_private_todo_content(self) -> None:
        owner = User.objects.create_user(username='pr09_private_owner', password='pw')
        services.set_todo_list_privacy(owner, is_private=True)
        Todo.objects.create(title='ULTRA_SECRET_TODO_XYZ', owner=owner)
        viewer = User.objects.create_user(username='pr09_viewer2', password='secret')
        self.client.login(username='pr09_viewer2', password='secret')
        response = self.client.get('/users/search/', {'q': 'pr09_private'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pr09_private_owner')
        self.assertNotContains(response, 'ULTRA_SECRET_TODO_XYZ')

    def test_public_user_todo_list_visible_for_authenticated_viewer(self) -> None:
        owner = User.objects.create_user(username='pr09_public_owner', password='pw')
        viewer = User.objects.create_user(username='pr09_public_viewer', password='secret')
        services.set_todo_list_privacy(owner, is_private=False)
        Todo.objects.create(title='Visible on public list', owner=owner)
        self.client.login(username='pr09_public_viewer', password='secret')
        response = self.client.get(f'/users/{owner.username}/todos/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visible on public list')

    def test_public_user_todo_list_redirects_anonymous_to_login(self) -> None:
        owner = User.objects.create_user(username='pr09_anon_owner', password='pw')
        services.set_todo_list_privacy(owner, is_private=False)
        response = self.client.get(f'/users/{owner.username}/todos/')
        self.assertRedirects(
            response,
            f'/auth/login/?next=/users/{owner.username}/todos/',
            fetch_redirect_response=False,
        )

    def test_private_user_todo_list_blocked_for_other_users(self) -> None:
        owner = User.objects.create_user(username='pr09_blocked_owner', password='pw')
        viewer = User.objects.create_user(username='pr09_blocked_viewer', password='secret')
        services.set_todo_list_privacy(owner, is_private=True)
        Todo.objects.create(title='Hidden private item', owner=owner)
        self.client.login(username='pr09_blocked_viewer', password='secret')
        response = self.client.get(f'/users/{owner.username}/todos/')
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, 'Hidden private item', status_code=404)


@unittest.skipUnless(
    connection.vendor == 'postgresql',
    'Hybrid search uses pg_trgm and SearchVector',
)
@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class Pr09OwnerTodoSearchTests(TestCase):
    def test_owner_specific_todo_search_respects_privacy(self) -> None:
        owner = User.objects.create_user(username='pr09_search_owner', password='pw')
        viewer = User.objects.create_user(username='pr09_search_viewer', password='secret')
        services.set_todo_list_privacy(owner, is_private=True)
        Todo.objects.create(title='Owner secret alpha', notes='alpha', owner=owner)
        Todo.objects.create(title='Viewer alpha', notes='alpha', owner=viewer)
        self.client.login(username='pr09_search_viewer', password='secret')
        response = self.client.get(
            f'/users/{owner.username}/todos/',
            {'q': 'alpha'},
        )
        self.assertEqual(response.status_code, 404)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class UserSettingsViewTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username='viewer', password='secret')

    def test_settings_requires_login(self) -> None:
        response = self.client.get('/settings/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)

    def test_authenticated_get_shows_checkbox(self) -> None:
        self.client.login(username='viewer', password='secret')
        response = self.client.get('/settings/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Keep my Todo list private')

    def test_post_updates_privacy(self) -> None:
        self.client.login(username='viewer', password='secret')
        response = self.client.post('/settings/', {'is_todo_list_private': 'on'})
        self.assertEqual(response.status_code, 302)
        settings_row = UserSettings.objects.get(user=self.user)
        self.assertTrue(settings_row.is_todo_list_private)

        response = self.client.post('/settings/', {}, follow=False)
        self.assertEqual(response.status_code, 302)
        settings_row.refresh_from_db()
        self.assertFalse(settings_row.is_todo_list_private)

    def test_login_page_renders(self) -> None:
        response = self.client.get('/auth/login/')
        self.assertEqual(response.status_code, 200)


_COMPLEX_PASSWORD = 'n0OrdinaryHorseBatteryStaple!x'


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class SignupFormIntegrationTests(TestCase):
    def test_signup_get_renders(self) -> None:
        response = self.client.get('/auth/signup/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Full name')

    def test_signup_valid_creates_user_logs_in_redirects(self) -> None:
        normalized = User.objects.normalize_email('casey@example.com')
        expected_username = services.username_for_normalized_email(normalized)
        response = self.client.post(
            '/auth/signup/',
            {
                'name': 'Casey Rivera',
                'email': 'casey@example.com',
                'password': _COMPLEX_PASSWORD,
                'password_confirm': _COMPLEX_PASSWORD,
            },
        )
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        user = User.objects.get(email__iexact='casey@example.com')
        self.assertEqual(user.first_name, 'Casey Rivera')
        self.assertTrue(user.check_password(_COMPLEX_PASSWORD))
        self.assertTrue(UserSettings.objects.filter(user=user).exists())
        self.assertEqual(user.username, expected_username)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_duplicate_email_rejected(self) -> None:
        services.register_user(display_name='A', email='dup@example.com', password=_COMPLEX_PASSWORD)
        response = self.client.post(
            '/auth/signup/',
            {
                'name': 'B Bee',
                'email': 'dup@example.com',
                'password': _COMPLEX_PASSWORD,
                'password_confirm': _COMPLEX_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')

    def test_password_mismatch_rejected(self) -> None:
        response = self.client.post(
            '/auth/signup/',
            {
                'name': 'C Cee',
                'email': 'cee@example.com',
                'password': _COMPLEX_PASSWORD,
                'password_confirm': _COMPLEX_PASSWORD + 'x',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'match')

    def test_weak_password_rejected(self) -> None:
        weak = 'x'
        response = self.client.post(
            '/auth/signup/',
            {
                'name': 'D Dee',
                'email': 'dee@example.com',
                'password': weak,
                'password_confirm': weak,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'too short')
