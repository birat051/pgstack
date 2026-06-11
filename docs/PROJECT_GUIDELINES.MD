# pgstack — Best Practices

> Show, don't tell. Every rule below has a concrete example.
>
> **Architecture map:** see [`ARCHITECTURE.MD`](ARCHITECTURE.MD) for routes, views, services, Postgres feature paths, and Docker wiring.

---

## Directory structure

```
pgstack/
├── docker-compose.yml
├── docker-compose.override.yml     # local dev overrides (never committed with secrets)
├── Dockerfile
├── .env.example                    # committed — documents required vars, no real values
├── .env                            # never committed
├── .dockerignore
├── requirements/
│   ├── base.txt                    # shared across all environments
│   ├── dev.txt                     # -r base.txt + django-debug-toolbar, ipython
│   └── prod.txt                    # -r base.txt + gunicorn, sentry-sdk
├── manage.py
├── pgstack/                        # project config package
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py                 # shared settings
│   │   ├── dev.py                  # overrides for local Docker
│   │   └── prod.py                 # overrides for production
│   └── urls.py
└── todos/                          # one app per domain concept
    ├── __init__.py
    ├── admin.py
    ├── apps.py
    ├── consumers.py                # Channels WebSocket consumers
    ├── models.py
    ├── routing.py                  # WebSocket URL routing
    ├── services.py                 # business logic — never in views or models
    ├── worker.py                   # SKIP LOCKED job processor
    ├── views.py                    # thin — delegate to services.py
    ├── urls.py
    ├── migrations/
    │   ├── __init__.py
    │   ├── 0001_initial.py
    │   ├── 0002_add_gin_index.py   # one concern per migration
    │   └── 0003_notify_trigger.py
    ├── management/
    │   └── commands/
    │       ├── __init__.py
    │       └── run_worker.py
    ├── templates/
    │   └── todos/
    │       ├── base.html
    │       ├── index.html
    │       ├── search_results.html
    │       ├── dashboard.html
    │       └── queue_monitor.html
    └── tests/
        ├── __init__.py
        ├── test_models.py
        ├── test_views.py
        ├── test_search.py
        ├── test_worker.py
        └── test_consumers.py
```

---

## Python best practices

### Explicit over implicit

```python
# bad — what is x? what does True mean here?
def process(x, flag=True):
    ...

# good
def process_job(job: Job, notify_on_complete: bool = True) -> None:
    ...
```

---

### Type hints everywhere

```python
# bad
def get_pending_jobs(limit):
    return Job.objects.filter(status='queued')[:limit]

# good
from typing import QuerySet

def get_pending_jobs(limit: int = 10) -> QuerySet[Job]:
    return Job.objects.filter(status=JobStatus.QUEUED)[:limit]
```

---

### Use enums for choices — never raw strings

```python
# bad
todo.status = 'done'
if job.status == 'failed':
    ...

# good
from django.db import models

class TodoStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    DONE    = 'done',    'Done'
    OVERDUE = 'overdue', 'Overdue'

class JobStatus(models.TextChoices):
    QUEUED     = 'queued',      'Queued'
    PROCESSING = 'processing',  'Processing'
    DONE       = 'done',        'Done'
    FAILED     = 'failed',      'Failed'

todo.status = TodoStatus.DONE
if job.status == JobStatus.FAILED:
    ...
```

---

### Dataclasses for structured return values

```python
# bad — returning a raw dict is untyped and fragile
def get_stats():
    return {'total': 10, 'done': 4, 'overdue': 2}

# good
from dataclasses import dataclass

@dataclass(frozen=True)
class TodoStats:
    total: int
    done: int
    overdue: int

def get_stats() -> TodoStats:
    row = Todo.objects.raw("SELECT * FROM todo_stats")[0]
    return TodoStats(total=row.total, done=row.done, overdue=row.overdue_count)
```

---

### Keep functions small and single-purpose

```python
# bad — one function doing three things
def handle_job(job_id: int) -> None:
    job = Job.objects.select_for_update(skip_locked=True).get(id=job_id)
    job.status = JobStatus.PROCESSING
    job.save()
    if job.job_type == 'send_reminder':
        # ... send logic inline ...
        pass
    job.status = JobStatus.DONE
    job.processed_at = timezone.now()
    job.save()

# good — each function has one reason to change
def acquire_job(job_id: int) -> Job | None:
    return (
        Job.objects
        .select_for_update(skip_locked=True)
        .filter(id=job_id, status=JobStatus.QUEUED)
        .first()
    )

def mark_processing(job: Job) -> None:
    Job.objects.filter(id=job.id).update(status=JobStatus.PROCESSING)

def mark_complete(job: Job) -> None:
    Job.objects.filter(id=job.id).update(
        status=JobStatus.DONE,
        processed_at=timezone.now(),
    )

def mark_failed(job: Job) -> None:
    Job.objects.filter(id=job.id).update(status=JobStatus.FAILED)
```

---

### Settings via environment — never hardcoded

```python
# bad
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'pgstack',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': 'localhost',
    }
}

# good — pgstack/settings/base.py
import dj_database_url
from decouple import config

DATABASES = {
    'default': dj_database_url.parse(
        config('DATABASE_URL'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

SECRET_KEY = config('SECRET_KEY')
DEBUG      = config('DEBUG', default=False, cast=bool)
```

---

## Django best practices

### Fat services, thin views

Views should read a request, call a service, return a response. Nothing more.

```python
# bad — business logic bleeding into the view
def create_todo(request):
    title = request.POST['title']
    todo = Todo.objects.create(title=title, status='pending')
    Job.objects.create(todo=todo, job_type='send_reminder', status='queued')
    return redirect('/')

# good — view delegates entirely to service
# todos/views.py
from todos.services import create_todo_with_job

def create_todo(request):
    if request.method == 'POST':
        create_todo_with_job(
            title=request.POST['title'],
            notes=request.POST.get('notes', ''),
        )
    return redirect('/')

# todos/services.py
from django.db import transaction

@transaction.atomic
def create_todo_with_job(title: str, notes: str = '') -> Todo:
    todo = Todo.objects.create(title=title, notes=notes)
    # trigger handles Job insert via Postgres — no ORM call needed here
    return todo
```

---

### Use `update()` instead of `save()` for targeted writes

```python
# bad — loads the object, marks every field dirty, writes all columns
job = Job.objects.get(id=job_id)
job.status = JobStatus.DONE
job.processed_at = timezone.now()
job.save()

# good — single UPDATE touching only the columns that changed
Job.objects.filter(id=job_id).update(
    status=JobStatus.DONE,
    processed_at=timezone.now(),
)
```

---

### Always use `select_related` / `prefetch_related` — never query in a loop

```python
# bad — N+1: one query per job to fetch the related todo
jobs = Job.objects.all()
for job in jobs:
    print(job.todo.title)   # new query every iteration

# good — two queries total regardless of result size
jobs = Job.objects.select_related('todo').all()
for job in jobs:
    print(job.todo.title)   # already in memory
```

---

### Wrap multi-step DB writes in `transaction.atomic`

```python
# bad — if the Job insert fails, the Todo is orphaned
def create_todo_with_job(title: str) -> Todo:
    todo = Todo.objects.create(title=title)
    Job.objects.create(todo=todo, job_type='send_reminder')
    return todo

# good — both writes succeed or both roll back
from django.db import transaction

@transaction.atomic
def create_todo_with_job(title: str) -> Todo:
    todo = Todo.objects.create(title=title)
    Job.objects.create(todo=todo, job_type='send_reminder')
    return todo
```

---

### Keep migrations focused — one concern per migration

```
# bad — one migration doing everything
0002_add_search_vector_gin_index_notify_trigger_stats_view.py

# good — one migration per concern, easy to bisect and roll back
0002_add_search_vector_column.py
0003_add_gin_index.py
0004_add_notify_trigger.py
0005_add_todo_stats_view.py
```

Each `RunSQL` migration must include a `reverse_sql`:

```python
# todos/migrations/0003_add_gin_index.py
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [('todos', '0002_add_search_vector_column')]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE INDEX todos_search_gin
                ON todos_todo USING GIN(search_vector);
            """,
            reverse_sql="DROP INDEX IF EXISTS todos_search_gin;",
        )
    ]
```

---

### Custom managers for reusable querysets

```python
# bad — filter logic scattered across views and services
Job.objects.filter(status='queued').order_by('created_at')

# good — one place to change the definition of "pending"
class JobQuerySet(models.QuerySet):
    def queued(self) -> 'JobQuerySet':
        return self.filter(status=JobStatus.QUEUED).order_by('created_at')

    def failed(self) -> 'JobQuerySet':
        return self.filter(status=JobStatus.FAILED)

class JobManager(models.Manager):
    def get_queryset(self) -> JobQuerySet:
        return JobQuerySet(self.model, using=self._db)

class Job(models.Model):
    objects = JobManager()
    ...

# usage
Job.objects.queued().first()
Job.objects.failed().count()
```

---

## Postgres best practices

### Always reference columns explicitly in `RunSQL`

```sql
-- bad — SELECT * breaks if columns are added or reordered
SELECT * FROM todo_stats;

-- good
SELECT status, total, done_count, overdue_count FROM todo_stats;
```

---

### Use `CONCURRENTLY` when refreshing materialized views

```sql
-- bad — locks the view for reads during the entire refresh
REFRESH MATERIALIZED VIEW todo_stats;

-- good — reads continue unblocked; requires a unique index on the view
REFRESH MATERIALIZED VIEW CONCURRENTLY todo_stats;
```

---

### Use `COALESCE` in triggers — nulls break `tsvector`

```sql
-- bad — NULL in notes causes the whole vector to be NULL
to_tsvector('english', title || ' ' || notes)

-- good
to_tsvector('english',
    coalesce(NEW.title, '') || ' ' || coalesce(NEW.notes, '')
)
```

---

### Use `SKIP LOCKED` — never poll with a plain `SELECT`

```python
# bad — two workers can grab the same row; leads to double processing
job = Job.objects.filter(status=JobStatus.QUEUED).first()

# good — row is locked atomically; other workers skip it
with transaction.atomic():
    job = (
        Job.objects
        .select_for_update(skip_locked=True)
        .filter(status=JobStatus.QUEUED)
        .order_by('created_at')
        .first()
    )
```

---

### Validate `pg_notify` payload size

`pg_notify` payloads are capped at 8000 bytes. Sending a large `notes` field
will silently drop the notification.

```python
# bad — payload could exceed 8000 bytes
PERFORM pg_notify('todo_updates', row_to_json(NEW)::text);

# good — send only the id; consumer fetches the full row if needed
PERFORM pg_notify('todo_updates', json_build_object(
    'id',     NEW.id,
    'title',  NEW.title,
    'status', NEW.status
)::text);
```

---

### Index columns used in `WHERE` and `ORDER BY`

```python
# todos/models.py
class Job(models.Model):
    ...
    class Meta:
        indexes = [
            # workers always query by status + created_at
            models.Index(fields=['status', 'created_at'], name='job_status_created_idx'),
        ]
```

---

### Use `conn_max_age` and `conn_health_checks` in production

```python
# pgstack/settings/base.py
DATABASES = {
    'default': dj_database_url.parse(
        config('DATABASE_URL'),
        conn_max_age=600,       # reuse connections for 10 min — reduces TCP overhead
        conn_health_checks=True # drop stale connections before reuse
    )
}
```

---

## Docker best practices

### Split requirements by environment — never install dev tools in prod

```dockerfile
# Dockerfile
ARG ENV=prod
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/${ENV}.txt
```

```yaml
# docker-compose.yml (prod)
services:
  web:
    build:
      args:
        ENV: prod

# docker-compose.override.yml (dev — never committed with secrets)
services:
  web:
    build:
      args:
        ENV: dev
    volumes:
      - .:/app          # live reload
```

---

### Wait for Postgres to be ready — never rely on `depends_on` alone

```python
# todos/management/commands/wait_for_db.py
import time
from django.db import connections
from django.db.utils import OperationalError
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        db_conn = None
        while not db_conn:
            try:
                db_conn = connections['default']
                db_conn.cursor()
            except OperationalError:
                self.stdout.write('Waiting for database...')
                time.sleep(1)
        self.stdout.write('Database ready.')
```

```dockerfile
# Dockerfile entrypoint
CMD ["sh", "-c", "python manage.py wait_for_db && python manage.py migrate && daphne -b 0.0.0.0 -p 8000 pgstack.asgi:application"]
```

---

### Use a named volume for Postgres data — never an anonymous volume

```yaml
# bad — anonymous volume, data lost on docker compose down
services:
  db:
    image: postgres:16

# good — named volume persists across restarts
services:
  db:
    image: postgres:16
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

---

## Testing best practices

### Use `pytest-django` and `TestCase` — never hit the real DB in unit tests

```python
# todos/tests/test_worker.py
from django.test import TestCase
from todos.models import Todo, Job, JobStatus
from todos.worker import acquire_job, mark_complete

class SkipLockedWorkerTest(TestCase):
    def test_acquire_job_returns_queued_job(self):
        todo = Todo.objects.create(title='Test', status='pending')
        job  = Job.objects.create(todo=todo, job_type='send_reminder')
        acquired = acquire_job()
        self.assertEqual(acquired.id, job.id)

    def test_mark_complete_sets_processed_at(self):
        todo = Todo.objects.create(title='Test', status='pending')
        job  = Job.objects.create(todo=todo, job_type='send_reminder')
        mark_complete(job)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.DONE)
        self.assertIsNotNone(job.processed_at)
```

---

### Test search with real Postgres — `SearchVector` does not work with SQLite

```python
# todos/tests/test_search.py
from django.test import TestCase
from todos.models import Todo

class FullTextSearchTest(TestCase):
    def setUp(self):
        Todo.objects.create(title='Buy groceries', notes='milk eggs bread')
        Todo.objects.create(title='Fix Postgres trigger', notes='tsvector gin index')

    def test_search_returns_ranked_results(self):
        response = self.client.get('/search/', {'q': 'postgres'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Postgres')

    def test_search_returns_empty_for_no_match(self):
        response = self.client.get('/search/', {'q': 'xyznothing'})
        self.assertQuerySetEqual(response.context['todos'], [])
```

---

## Task tracking

### Mark every task done immediately after execution — not at the end of a PR

The checklist in `pgstack_checklist.md` is the single source of truth for progress.
A task is only done when it is verified to work, not when the code is written.

```
# bad — marking done before verifying
- [x] Add GIN index        ← marked done while writing the migration
- [ ] Test index is used   ← separate step, easy to skip

# good — mark done only after the test passes
- [ ] Add GIN index
- [ ] Run EXPLAIN ANALYZE SELECT … to confirm index is hit
- [x] Add GIN index        ← marked done after EXPLAIN confirms it
```

**The rule:** for each subtask in the checklist, work top to bottom. Check the box
only after you have run the relevant verification step — a passing test, a `psql`
query, a browser check, or a Docker smoke test. Never batch-tick at the end of a
session.

**For Postgres-specific tasks**, verification means running the query manually:

```sql
-- after adding the GIN index, confirm it exists
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'todos_todo';

-- after adding a trigger, confirm it is registered
SELECT trigger_name, event_manipulation, action_timing
FROM information_schema.triggers
WHERE event_object_table = 'todos_todo';

-- after creating the materialized view, confirm it is populated
SELECT * FROM todo_stats;

-- after a SKIP LOCKED worker run, confirm job status updated
SELECT id, status, processed_at FROM todos_job ORDER BY created_at DESC LIMIT 5;
```

**For Django tasks**, verification means the dev server responds correctly inside Docker:

```bash
# after adding a view, confirm it returns 200
docker compose exec web python manage.py shell -c "
from django.test import Client
r = Client().get('/search/?q=test')
print(r.status_code)
"

# after a migration, confirm no pending migrations remain
docker compose run web python manage.py migrate --check
```

---

## Checklist before every PR

- [ ] Every subtask in `pgstack_checklist.md` for this PR is ticked
- [ ] No raw strings for status values — use `TodoStatus` / `JobStatus` enums
- [ ] No business logic in views — services only
- [ ] Every `RunSQL` migration has a `reverse_sql`
- [ ] No `save()` where `update()` would do
- [ ] No querysets without `select_related` when traversing FK relations
- [ ] Multi-step DB writes wrapped in `transaction.atomic`
- [ ] `pg_notify` payloads are under 8000 bytes
- [ ] New indexed columns declared in `Meta.indexes`
- [ ] Tests added for the changed behaviour
- [ ] `docker compose down -v && docker compose up --build` still passes
