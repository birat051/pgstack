import unittest

from django.db import connection
from django.test import TestCase, override_settings

from todos.models import Todo, TodoStatus


@unittest.skipUnless(
    connection.vendor == 'postgresql',
    'Hybrid search uses pg_trgm and SearchVector',
)
@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class HybridSearchTests(TestCase):
    def test_typo_tolerance_finds_milk(self) -> None:
        Todo.objects.create(title='Buy milk', notes='Organic dairy')
        response = self.client.get('/search/', {'q': 'milc'})
        self.assertEqual(response.status_code, 200)
        todos = list(response.context['todos'])
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0].title, 'Buy milk')

    def test_prefix_finds_milk(self) -> None:
        Todo.objects.create(title='Buy milk', notes='Organic dairy')
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
        )
        fts_strong = Todo.objects.create(
            title='Meeting',
            notes='alpha bravo unique',
            status=TodoStatus.PENDING,
        )
        response = self.client.get('/search/', {'q': 'alpha'})
        self.assertEqual(response.status_code, 200)
        ordered = list(response.context['todos'].values_list('id', flat=True))
        self.assertIn(fts_strong.id, ordered)
        self.assertIn(fuzzy_only.id, ordered)
        self.assertLess(ordered.index(fts_strong.id), ordered.index(fuzzy_only.id))

    def test_gibberish_returns_empty(self) -> None:
        Todo.objects.create(title='Buy milk', notes='Organic dairy')
        response = self.client.get('/search/', {'q': 'zzzqqqnonmatch987654'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['todos']), 0)

    def test_regression_lexical_notes_match(self) -> None:
        Todo.objects.create(title='Buy groceries', notes='milk eggs bread')
        Todo.objects.create(title='Fix Postgres trigger', notes='tsvector gin index')
        response = self.client.get('/search/', {'q': 'postgres'})
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context['todos']]
        self.assertIn('Fix Postgres trigger', titles)
