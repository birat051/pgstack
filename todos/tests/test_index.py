from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from todos.models import Todo, TodoStatus


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class IndexViewTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = get_user_model().objects.create_user(
            username='todolist_owner',
            password='testpass123!',
            email='owner@example.com',
        )

    def test_root_returns_ok(self) -> None:
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_root_lists_recent_todos(self) -> None:
        Todo.objects.create(
            title='First',
            notes='',
            status=TodoStatus.PENDING,
            owner=self.owner,
        )
        self.client.login(
            username='todolist_owner',
            password='testpass123!',
        )
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'First')

    def test_root_hides_todos_for_anonymous_visitor(self) -> None:
        Todo.objects.create(
            title='Private row',
            notes='',
            status=TodoStatus.PENDING,
            owner=self.owner,
        )
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Private row')

    def test_root_shows_only_own_todos_when_logged_in(self) -> None:
        other = get_user_model().objects.create_user(
            username='neighbor',
            password='testpass123!',
            email='n@example.com',
        )
        Todo.objects.create(
            title='Neighbor only',
            notes='',
            status=TodoStatus.PENDING,
            owner=other,
        )
        self.client.login(
            username='todolist_owner',
            password='testpass123!',
        )
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Neighbor only')

    def test_anonymous_post_create_redirects_to_login(self) -> None:
        response = self.client.post('/', {'title': 'Leak', 'notes': ''})
        self.assertRedirects(
            response,
            '/auth/login/?next=/',
            fetch_redirect_response=False,
        )

    def test_authenticated_post_creates_owned_todo(self) -> None:
        self.client.login(
            username='todolist_owner',
            password='testpass123!',
        )
        response = self.client.post(
            '/',
            {'title': 'From form', 'notes': 'Owned note'},
        )
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        todo = Todo.objects.get(title='From form')
        self.assertEqual(todo.owner_id, self.owner.pk)
        self.assertEqual(todo.notes, 'Owned note')

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
