"""Todo CRUD/query helpers — business logic stays here, not views."""

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.postgres.search import (
    SearchHeadline,
    SearchQuery,
    SearchRank,
    TrigramSimilarity,
    TrigramWordSimilarity,
)
from django.db import models
from django.db.models import Case, Count, F, Q, QuerySet, Value, When
from django.db.models.functions import Greatest

from todos.models import Job, Todo, TodoStatus

QUEUE_MONITOR_LIMIT = 75


INDEX_PAGE_LIMIT = 50


def todo_queryset_for_actor(
    user: AbstractBaseUser | AnonymousUser,
) -> QuerySet[Todo]:
    """
    Visibility base for list + search: authenticated users see only owned rows.

    Public / third-party list views (PR 09) extend this in one place rather than
    re-scoping ad hoc in each view.
    """
    if not user.is_authenticated:
        return Todo.objects.none()
    return Todo.objects.filter(owner_id=user.pk).select_related('owner')


def list_todos_for_user(
    user: AbstractBaseUser | AnonymousUser,
    limit: int = INDEX_PAGE_LIMIT,
) -> QuerySet[Todo]:
    return todo_queryset_for_actor(user).order_by('-created_at')[:limit]


def create_todo(
    *,
    owner: AbstractBaseUser,
    title: str,
    notes: str = '',
) -> Todo:
    """Create a Todo row owned by ``owner`` in a single write."""
    return Todo.objects.create(
        owner_id=owner.pk,
        title=title.strip(),
        notes=(notes or '').strip(),
        status=TodoStatus.PENDING,
    )


def dashboard_counts_for_viewer(
    viewer: User,
    *,
    todo_list_owner: User | None = None,
) -> dict[str, int]:
    """
    Aggregate ``Todo`` rows by ``status`` for the dashboard cards.

    When ``todo_list_owner`` is set, callers must enforce
    ``accounts.services.can_view_todo_list(viewer, todo_list_owner)`` (typically 404).

    Until PR 12 reads from a materialized view, aggregates run on the owning queryset.
    """
    status_keys = [choice.value for choice in TodoStatus]
    counts: dict[str, int] = dict.fromkeys(status_keys, 0)
    qs: QuerySet[Todo]
    if todo_list_owner is None:
        qs = todo_queryset_for_actor(viewer)
    else:
        qs = Todo.objects.filter(owner_id=todo_list_owner.pk)
    grouped = qs.values('status').annotate(total=Count('id'))
    for row in grouped:
        status_key = row['status']
        if status_key in counts:
            counts[status_key] = row['total']
    return counts


def list_jobs_for_user(
    user: AbstractBaseUser | AnonymousUser,
    *,
    limit: int = QUEUE_MONITOR_LIMIT,
) -> QuerySet[Job]:
    if not user.is_authenticated:
        return Job.objects.none()
    return (
        Job.objects.filter(todo__owner_id=user.pk)
        .select_related('todo')
        .order_by('-created_at')[:limit]
    )


# pg_trgm similarity is 0–1; higher = fewer fuzzy matches (less noise).
TRIGRAM_THRESHOLD = 0.3
SEARCH_RESULTS_LIMIT = 50


def search_todos(
    q: str,
    *,
    user: AbstractBaseUser | AnonymousUser,
) -> QuerySet[Todo]:
    """
    Full-text matches rank first; trigram (typo + substring/prefix-style) fills in the rest.

    Results are limited to ``todo_queryset_for_actor(user)`` (the current user's todos
    until PR 09 adds broader visibility rules in that helper).

    Extensible: add fields to `Todo.search_document` (and the DB trigger for `search_vector`).
    """
    base = todo_queryset_for_actor(user)
    q = (q or '').strip()
    if not q:
        return base.none()

    search_query = SearchQuery(q, search_type='websearch', config='english')
    trigram_score = Greatest(
        TrigramSimilarity(F('search_document'), Value(q)),
        TrigramWordSimilarity(Value(q), F('search_document')),
    )

    return (
        base
        .annotate(
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
