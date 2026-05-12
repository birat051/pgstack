from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from todos.models import Todo, TodoStatus


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class IndexViewTests(TestCase):
    def test_root_returns_ok(self) -> None:
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_root_lists_recent_todos(self) -> None:
        Todo.objects.create(title='First', notes='', status=TodoStatus.PENDING)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'First')

    def test_logout_post_redirects_login_and_clears_session(self) -> None:
        get_user_model().objects.create_user(
            username='logmeout',
            password='n0OrdinaryHorseBatteryStaple!x',
            email='out@example.com',
        )
        self.client.login(username='logmeout', password='n0OrdinaryHorseBatteryStaple!x')
        self.assertIn('_auth_user_id', self.client.session)
        response = self.client.post('/auth/logout/')
        self.assertRedirects(response, '/auth/login/', fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_get_logs_out_and_redirects_to_login_when_authenticated(self) -> None:
        get_user_model().objects.create_user(
            username='getlogout',
            password='n0OrdinaryHorseBatteryStaple!x',
            email='getout@example.com',
        )
        self.client.login(username='getlogout', password='n0OrdinaryHorseBatteryStaple!x')
        response = self.client.get('/auth/logout/')
        self.assertRedirects(response, '/auth/login/', fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_get_redirects_login_when_anonymous(self) -> None:
        response = self.client.get('/auth/logout/')
        self.assertRedirects(response, '/auth/login/', fetch_redirect_response=False)
