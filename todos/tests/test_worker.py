from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase

from todos.models import Job, JobStatus, Todo, TodoStatus
from todos.worker import acquire_job, mark_complete, process_one_job


class SkipLockedWorkerTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = get_user_model().objects.create_user(
            username='worker_owner',
            password='testpass123!',
            email='worker@example.com',
        )

    def test_acquire_job_returns_queued_job(self) -> None:
        todo = Todo.objects.create(
            title='Test',
            status=TodoStatus.PENDING,
            owner=self.owner,
        )
        job = Job.objects.get(todo=todo, status=JobStatus.QUEUED)
        acquired = acquire_job()
        self.assertIsNotNone(acquired)
        assert acquired is not None
        self.assertEqual(acquired.id, job.id)

    def test_mark_complete_sets_processed_at(self) -> None:
        todo = Todo.objects.create(
            title='Test',
            status=TodoStatus.PENDING,
            owner=self.owner,
        )
        job = Job.objects.get(todo=todo, status=JobStatus.QUEUED)
        mark_complete(job)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.DONE)
        self.assertIsNotNone(job.processed_at)

    def test_process_one_job_marks_done(self) -> None:
        todo = Todo.objects.create(
            title='Process me',
            status=TodoStatus.PENDING,
            owner=self.owner,
        )
        job = Job.objects.get(todo=todo, status=JobStatus.QUEUED)
        self.assertTrue(process_one_job())
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.DONE)
        self.assertIsNotNone(job.processed_at)

    def test_process_one_job_returns_false_when_queue_empty(self) -> None:
        self.assertFalse(process_one_job())


class SkipLockedConcurrencyTest(TransactionTestCase):
    """Simulate multiple workers; requires commits visible across threads."""

    def setUp(self) -> None:
        super().setUp()
        self.owner = get_user_model().objects.create_user(
            username='concurrency_owner',
            password='testpass123!',
            email='concurrency@example.com',
        )

    def test_three_workers_process_ten_jobs_without_double_processing(self) -> None:
        todos = [
            Todo.objects.create(
                title=f'Concurrent {index}',
                status=TodoStatus.PENDING,
                owner=self.owner,
            )
            for index in range(10)
        ]
        jobs = list(Job.objects.filter(todo__in=todos).order_by('id'))
        self.assertEqual(len(jobs), 10)

        def _process_one_job_in_thread(_: int) -> bool:
            try:
                return process_one_job()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=3) as pool:
            processed = list(pool.map(_process_one_job_in_thread, range(30)))

        self.assertGreaterEqual(sum(processed), 10)
        for job in jobs:
            job.refresh_from_db()
            self.assertEqual(job.status, JobStatus.DONE)
            self.assertIsNotNone(job.processed_at)

        self.assertEqual(
            Job.objects.filter(todo__in=todos, status=JobStatus.DONE).count(),
            10,
        )
        self.assertEqual(
            Job.objects.filter(todo__in=todos, status=JobStatus.QUEUED).count(),
            0,
        )
        self.assertEqual(
            Job.objects.filter(todo__in=todos, status=JobStatus.PROCESSING).count(),
            0,
        )


class RunWorkerCommandTest(TestCase):
    @patch('todos.management.commands.run_worker.process_jobs')
    def test_run_worker_calls_process_jobs_in_loop(self, mock_process_jobs: object) -> None:
        mock_process_jobs.side_effect = KeyboardInterrupt
        out = StringIO()
        call_command('run_worker', stdout=out)
        mock_process_jobs.assert_called_once()
        self.assertIn('Worker started', out.getvalue())
        self.assertIn('Worker stopped', out.getvalue())
