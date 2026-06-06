"""Todo CRUD/query helpers — business logic stays here, not views."""

from dataclasses import dataclass

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.postgres.search import (
    SearchHeadline,
    SearchQuery,
    SearchRank,
    TrigramSimilarity,
    TrigramWordSimilarity,
)
from django.db import connection, models
from django.db.models import Case, F, Q, QuerySet, Value, When
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


def list_todos_for_owner(
    owner: User,
    limit: int = INDEX_PAGE_LIMIT,
) -> QuerySet[Todo]:
    """Recent todos for ``owner``; callers must enforce list visibility."""
    return (
        Todo.objects.filter(owner_id=owner.pk)
        .select_related('owner')
        .order_by('-created_at')[:limit]
    )


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


@dataclass(frozen=True)
class TodoStatsRow:
    status: str
    total: int
    overdue_count: int
    done_count: int


def fetch_todo_stats_for_owner(owner_id: int) -> list[TodoStatsRow]:
    """Read pre-computed per-status counts from the ``todo_stats`` materialized view."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, total, overdue_count, done_count
            FROM todo_stats
            WHERE owner_id = %s
            """,
            [owner_id],
        )
        return [
            TodoStatsRow(
                status=row[0],
                total=row[1],
                overdue_count=row[2],
                done_count=row[3],
            )
            for row in cursor.fetchall()
        ]


def dashboard_counts_for_viewer(
    viewer: User,
    *,
    todo_list_owner: User | None = None,
) -> dict[str, int]:
    """
    Aggregate per-status totals for the dashboard cards from ``todo_stats``.

    When ``todo_list_owner`` is set, callers must enforce
    ``accounts.services.can_view_todo_list(viewer, todo_list_owner)`` (typically 404).
    """
    owner_id = (todo_list_owner or viewer).pk
    status_keys = [choice.value for choice in TodoStatus]
    counts: dict[str, int] = dict.fromkeys(status_keys, 0)
    for row in fetch_todo_stats_for_owner(owner_id):
        if row.status in counts:
            counts[row.status] = row.total
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


def _todo_search_on_queryset(base: QuerySet[Todo], q: str) -> QuerySet[Todo]:
    """Run hybrid FTS + trigram search on an already-scoped queryset."""
    term = (q or '').strip()
    if not term:
        return base.none()

    search_query = SearchQuery(term, search_type='websearch', config='english')
    trigram_score = Greatest(
        TrigramSimilarity(F('search_document'), Value(term)),
        TrigramWordSimilarity(Value(term), F('search_document')),
    )

    return (
        base.annotate(
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


def search_todos(
    q: str,
    *,
    user: AbstractBaseUser | AnonymousUser,
    list_owner: User | None = None,
) -> QuerySet[Todo]:
    """
    Full-text matches rank first; trigram (typo + substring/prefix-style) fills in the rest.

    When ``list_owner`` is omitted, results are limited to ``todo_queryset_for_actor(user)``
    (the signed-in user's own todos). When set, search runs only within that owner's rows;
    callers must enforce ``accounts.services.can_view_todo_list(user, list_owner)``.

    Extensible: add fields to `Todo.search_document` (and the DB trigger for `search_vector`).
    """
    if list_owner is not None:
        base = Todo.objects.filter(owner_id=list_owner.pk).select_related('owner')
    else:
        base = todo_queryset_for_actor(user)
    return _todo_search_on_queryset(base, q)
