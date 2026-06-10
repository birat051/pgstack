from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.services import set_todo_list_privacy
from todos.models import Job, JobStatus, Todo, TodoStatus
from todos.pg_notify_security import todo_update_payload_allowed_for_user
from todos.services import QUEUE_MONITOR_LIMIT


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class TodoNotifyPayloadSecurityTests(TestCase):
    def test_accepts_matching_owner_integer(self) -> None:
        raw = '{"id": 1, "owner_id": 42, "title": "x", "status": "pending"}'
        self.assertTrue(todo_update_payload_allowed_for_user(raw, viewer_pk=42))
        self.assertFalse(todo_update_payload_allowed_for_user(raw, viewer_pk=99))

    def test_accepts_matching_owner_digit_string(self) -> None:
        raw = '{"id": 1, "owner_id": "7", "title": "x", "status": "pending"}'
        self.assertTrue(todo_update_payload_allowed_for_user(raw, viewer_pk=7))

    def test_rejects_missing_owner_id_or_invalid_json(self) -> None:
        self.assertFalse(todo_update_payload_allowed_for_user('{"id": 1}', viewer_pk=1))
        self.assertFalse(todo_update_payload_allowed_for_user('not-json', viewer_pk=1))
        self.assertFalse(todo_update_payload_allowed_for_user('', viewer_pk=1))
        self.assertFalse(todo_update_payload_allowed_for_user(None, viewer_pk=1))


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class DashboardViewTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.alice = get_user_model().objects.create_user(
            username='dash_alice',
            password='testpass123!',
            email='alice@example.com',
        )
        self.bob = get_user_model().objects.create_user(
            username='dash_bob',
            password='testpass123!',
            email='bob@example.com',
        )

    def test_dashboard_redirects_when_anonymous(self) -> None:
        response = self.client.get('/dashboard/')
        self.assertRedirects(
            response,
            '/auth/login/?next=/dashboard/',
            fetch_redirect_response=False,
        )

    def test_dashboard_counts_own_todos_only(self) -> None:
        Todo.objects.create(
            title='A1',
            owner=self.alice,
            status=TodoStatus.PENDING,
        )
        Todo.objects.create(
            title='A2',
            owner=self.alice,
            status=TodoStatus.DONE,
        )
        Todo.objects.create(
            title='B_only',
            owner=self.bob,
            status=TodoStatus.PENDING,
        )
        self.client.login(username='dash_alice', password='testpass123!')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        counts = response.context['counts']
        self.assertEqual(counts[TodoStatus.PENDING.value], 1)
        self.assertEqual(counts[TodoStatus.DONE.value], 1)

    def test_dashboard_username_private_foreign_list_is_404(self) -> None:
        Todo.objects.create(
            title='secret',
            owner=self.bob,
            status=TodoStatus.PENDING,
        )
        self.client.login(username='dash_alice', password='testpass123!')
        response = self.client.get('/dashboard/', {'username': self.bob.username})
        self.assertEqual(response.status_code, 404)

    def test_dashboard_username_public_foreign_list_allowed(self) -> None:
        set_todo_list_privacy(self.bob, is_private=False)
        Todo.objects.create(
            title='public bob',
            owner=self.bob,
            status=TodoStatus.PENDING,
        )
        self.client.login(username='dash_alice', password='testpass123!')
        response = self.client.get('/dashboard/', {'username': self.bob.username})
        self.assertEqual(response.status_code, 200)
        counts = response.context['counts']
        self.assertEqual(counts[TodoStatus.PENDING.value], 1)
        self.assertEqual(response.context['view_username'], self.bob.username)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class QueueMonitorViewTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.alice = get_user_model().objects.create_user(
            username='q_alice',
            password='testpass123!',
            email='qalice@example.com',
        )
        self.bob = get_user_model().objects.create_user(
            username='q_bob',
            password='testpass123!',
            email='qbob@example.com',
        )

    def test_queue_redirects_when_anonymous(self) -> None:
        response = self.client.get('/queue/')
        self.assertRedirects(
            response,
            '/auth/login/?next=/queue/',
            fetch_redirect_response=False,
        )

    def test_queue_shows_jobs_for_own_todos_only(self) -> None:
        t_a = Todo.objects.create(title='Ja', owner=self.alice)
        Todo.objects.create(title='Jb', owner=self.bob)
        self.client.login(username='q_alice', password='testpass123!')
        response = self.client.get('/queue/')
        self.assertEqual(response.status_code, 200)
        rows = list(response.context['jobs'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].todo_id, t_a.pk)
        self.assertEqual(rows[0].status, JobStatus.QUEUED)

    def test_queue_limits_to_latest_jobs(self) -> None:
        for i in range(QUEUE_MONITOR_LIMIT + 5):
            Todo.objects.create(title=f'T{i}', owner=self.alice)
        self.client.login(username='q_alice', password='testpass123!')
        response = self.client.get('/queue/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(list(response.context['jobs'])), QUEUE_MONITOR_LIMIT)

    def test_queue_renders_status_badges_and_processed_at(self) -> None:
        todo = Todo.objects.create(title='Badge test', owner=self.alice)
        job = Job.objects.get(todo=todo)
        Job.objects.filter(pk=job.pk).update(
            status=JobStatus.DONE,
            processed_at=job.created_at,
        )
        job.refresh_from_db()
        self.client.login(username='q_alice', password='testpass123!')
        response = self.client.get('/queue/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'badge-done')
        self.assertContains(response, 'Badge test')
        self.assertContains(response, job.job_type)
        self.assertNotContains(response, '<td>—</td>')
