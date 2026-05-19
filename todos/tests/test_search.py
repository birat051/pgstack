import unittest

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings

from todos.models import Todo, TodoStatus


@unittest.skipUnless(
    connection.vendor == 'postgresql',
    'Hybrid search uses pg_trgm and SearchVector',
)
@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class HybridSearchTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = get_user_model().objects.create_user(
            username='search_owner',
            password='testpass123!',
            email='search@example.com',
        )
        self.client.login(username='search_owner', password='testpass123!')

    def test_typo_tolerance_finds_milk(self) -> None:
        Todo.objects.create(
            title='Buy milk', notes='Organic dairy', owner=self.owner
        )
        response = self.client.get('/search/', {'q': 'milc'})
        self.assertEqual(response.status_code, 200)
        todos = list(response.context['todos'])
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0].title, 'Buy milk')

    def test_prefix_finds_milk(self) -> None:
        Todo.objects.create(
            title='Buy milk', notes='Organic dairy', owner=self.owner
        )
        response = self.client.get('/search/', {'q': 'mil'})
        self.assertEqual(response.status_code, 200)
        todos = list(response.context['todos'])
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0].title, 'Buy milk')

    def test_fts_match_ranks_before_fuzzy_only(self) -> None:
        fuzzy_only = Todo.objects.create(
            title='Other',
            notes='alph typo almost',
            status=TodoStatus.PENDING,
            owner=self.owner,
        )
        fts_strong = Todo.objects.create(
            title='Meeting',
            notes='alpha bravo unique',
            status=TodoStatus.PENDING,
            owner=self.owner,
        )
        response = self.client.get('/search/', {'q': 'alpha'})
        self.assertEqual(response.status_code, 200)
        ordered = list(response.context['todos'].values_list('id', flat=True))
        self.assertIn(fts_strong.id, ordered)
        self.assertIn(fuzzy_only.id, ordered)
        self.assertLess(ordered.index(fts_strong.id), ordered.index(fuzzy_only.id))

    def test_gibberish_returns_empty(self) -> None:
        Todo.objects.create(
            title='Buy milk', notes='Organic dairy', owner=self.owner
        )
        response = self.client.get('/search/', {'q': 'zzzqqqnonmatch987654'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['todos']), 0)

    def test_regression_lexical_notes_match(self) -> None:
        Todo.objects.create(
            title='Buy groceries',
            notes='milk eggs bread',
            owner=self.owner,
        )
        Todo.objects.create(
            title='Fix Postgres trigger',
            notes='tsvector gin index',
            owner=self.owner,
        )
        response = self.client.get('/search/', {'q': 'postgres'})
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context['todos']]
        self.assertIn('Fix Postgres trigger', titles)

    def test_search_excludes_other_users_todos(self) -> None:
        other = get_user_model().objects.create_user(
            username='search_other',
            password='testpass123!',
            email='other@example.com',
        )
        Todo.objects.create(title='Shared phrase', notes='alpha', owner=self.owner)
        Todo.objects.create(title='Other list', notes='alpha bravo', owner=other)
        response = self.client.get('/search/', {'q': 'alpha'})
        titles = [t.title for t in response.context['todos']]
        self.assertIn('Shared phrase', titles)
        self.assertNotIn('Other list', titles)
