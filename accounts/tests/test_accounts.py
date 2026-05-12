from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase, override_settings

from accounts import services
from accounts.models import UserSettings


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
