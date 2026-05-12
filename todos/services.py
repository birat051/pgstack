"""Todo search: hybrid full-text (tsvector) + pg_trgm fallback."""

from django.contrib.postgres.search import (
    SearchHeadline,
    SearchQuery,
    SearchRank,
    TrigramSimilarity,
    TrigramWordSimilarity,
)
from django.db import models
from django.db.models import Case, F, Q, QuerySet, Value, When
from django.db.models.functions import Greatest

from todos.models import Todo

INDEX_PAGE_LIMIT = 50


def list_recent_todos(limit: int = INDEX_PAGE_LIMIT) -> QuerySet[Todo]:
    return Todo.objects.order_by('-created_at')[:limit]


# pg_trgm similarity is 0–1; higher = fewer fuzzy matches (less noise).
TRIGRAM_THRESHOLD = 0.3
SEARCH_RESULTS_LIMIT = 50


def search_todos(q: str) -> QuerySet[Todo]:
    """
    Full-text matches rank first; trigram (typo + substring/prefix-style) fills in the rest.
    Extensible: add fields to `Todo.search_document` (and the DB trigger for `search_vector`).
    """
    q = (q or '').strip()
    if not q:
        return Todo.objects.none()

    search_query = SearchQuery(q, search_type='websearch', config='english')
    trigram_score = Greatest(
        TrigramSimilarity(F('search_document'), Value(q)),
        TrigramWordSimilarity(Value(q), F('search_document')),
    )

    return (
        Todo.objects.annotate(
            rank=SearchRank(F('search_vector'), search_query),
            trigram_score=trigram_score,
            headline=SearchHeadline(
                F('search_document'),
                search_query,
                config='english',
            ),
        )
        .filter(
            Q(search_vector=search_query) | Q(trigram_score__gte=TRIGRAM_THRESHOLD)
        )
        .annotate(
            fts_tier=Case(
                When(rank__gt=0.0, then=Value(1)),
                default=Value(0),
                output_field=models.IntegerField(),
            ),
        )
        .order_by('-fts_tier', '-rank', '-trigram_score')[:SEARCH_RESULTS_LIMIT]
    )
