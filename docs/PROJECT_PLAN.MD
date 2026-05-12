# pgstack

> A TODO app that pushes Postgres to its limits — replacing Redis, Elasticsearch, SQS, and a cache layer with a single Postgres instance. Built with Django's MVT architecture. No Redis. No Elasticsearch. No Celery. No SQS.

---

## Stack

| Layer              | Tool                                       |
| ------------------ | ------------------------------------------ |
| Framework          | Django (MVT)                               |
| Database           | PostgreSQL                                 |
| Real-time          | Django Channels (ASGI)                     |
| Templates          | Django Templates                           |
| Background workers | Python threads / async workers (no Celery) |

---

## What Postgres replaces

| Replaces        | Postgres feature                                   | Phase |
| --------------- | -------------------------------------------------- | ----- |
| Elasticsearch   | `tsvector` + `tsquery` + GIN index + `ts_headline` | 2     |
| Redis Pub/Sub   | `pg_notify` + `LISTEN` + Django Channels           | 3     |
| Redis cache     | `MATERIALIZED VIEW` + concurrent refresh           | 4     |
| SQS / job queue | `SELECT FOR UPDATE SKIP LOCKED` + `NOTIFY`         | 5     |

---

## Phase 1 — Project Setup & Model (~1 hr)

**Goal:** Django project wired to Postgres, core models, zero extra services.

- `django-admin startproject pgstack`
- Install: `psycopg2-binary`, `channels`, `daphne`
- Create `todos` app — `python manage.py startapp todos`

### Models

```python
# todos/models.py

class Todo(models.Model):
    STATUS = [('pending','Pending'), ('done','Done'), ('overdue','Overdue')]
    title        = models.CharField(max_length=255)
    notes        = models.TextField(blank=True)
    status       = models.CharField(max_length=10, choices=STATUS, default='pending')
    due_date     = models.DateField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    search_vector = SearchVectorField(null=True)  # django.contrib.postgres


class Job(models.Model):
    STATUS = [('queued','Queued'), ('processing','Processing'), ('done','Done'), ('failed','Failed')]
    todo      = models.ForeignKey(Todo, on_delete=models.CASCADE)
    job_type  = models.CharField(max_length=50)   # e.g. 'send_reminder', 'mark_overdue'
    payload   = models.JSONField(default=dict)
    status    = models.CharField(max_length=12, choices=STATUS, default='queued')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True)
```

- Run migrations
- Configure `DATABASES` in `settings.py`

**Deliverable:** `python manage.py runserver` loads without errors.

---

## Phase 2 — Full-text Search (Replaces Elasticsearch) (~1.5 hr)

**Postgres features:** `tsvector`, `tsquery`, GIN index, `ts_headline`, `ts_rank`

### Migration — GIN index

```sql
CREATE INDEX pgstack_search_gin ON todos_todo USING GIN(search_vector);
```

### Trigger — keep search_vector in sync

```sql
CREATE OR REPLACE FUNCTION todos_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    to_tsvector('english',
      coalesce(NEW.title, '') || ' ' || coalesce(NEW.notes, '')
    );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER todos_search_trigger
BEFORE INSERT OR UPDATE ON todos_todo
FOR EACH ROW EXECUTE FUNCTION todos_search_vector_update();
```

### Django View

```python
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchHeadline

def search_todos(request):
    q = request.GET.get('q', '')
    todos = Todo.objects.annotate(
        rank=SearchRank('search_vector', SearchQuery(q)),
        headline=SearchHeadline('title', SearchQuery(q))
    ).filter(search_vector=SearchQuery(q)).order_by('-rank')
    return render(request, 'todos/search_results.html', {'todos': todos, 'q': q})
```

### Template

- `todos/search_results.html` — search bar + ranked results with highlighted terms

**Deliverable:** Ranked, highlighted search results. No Elasticsearch.

---

## Phase 3 — Live Sync via LISTEN/NOTIFY (Replaces Redis Pub/Sub) (~2 hr)

**Postgres features:** `pg_notify`, `LISTEN`
**Django feature:** Django Channels, ASGI

### ASGI setup

```python
# pgstack/asgi.py
from channels.routing import ProtocolTypeRouter, URLRouter
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter(websocket_urlpatterns),
})
```

### Trigger — fire notification on every write

```sql
CREATE OR REPLACE FUNCTION notify_todo_change() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('todo_updates', row_to_json(NEW)::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER todo_notify_trigger
AFTER INSERT OR UPDATE ON todos_todo
FOR EACH ROW EXECUTE FUNCTION notify_todo_change();
```

### Channels consumer — no Redis channel layer

```python
class TodoConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.listener = asyncio.ensure_future(self.listen_postgres())

    async def listen_postgres(self):
        conn = await asyncpg.connect(settings.DATABASE_URL)
        await conn.add_listener('todo_updates', self.on_notify)

    async def on_notify(self, conn, pid, channel, payload):
        await self.send(text_data=payload)
```

### Template

- `todos/index.html` — todo list with inline WebSocket script
- On message: update or prepend the relevant todo row in the DOM without a page reload

**Deliverable:** Two browser tabs, one Postgres instance. Create a todo in tab A — tab B updates instantly. No Redis.

---

## Phase 4 — Dashboard via Materialized View (Replaces Redis Cache) (~1 hr)

**Postgres features:** `MATERIALIZED VIEW`, `REFRESH MATERIALIZED VIEW CONCURRENTLY`

### Materialized view

```sql
CREATE MATERIALIZED VIEW todo_stats AS
SELECT
  status,
  COUNT(*)                                        AS total,
  COUNT(*) FILTER (WHERE due_date < NOW())        AS overdue_count,
  COUNT(*) FILTER (WHERE status = 'done')         AS done_count
FROM todos_todo
GROUP BY status;

CREATE UNIQUE INDEX ON todo_stats(status);
```

### Trigger — refresh after every write

```sql
CREATE OR REPLACE FUNCTION refresh_todo_stats() RETURNS trigger AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY todo_stats;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER refresh_stats_trigger
AFTER INSERT OR UPDATE OR DELETE ON todos_todo
FOR EACH ROW EXECUTE FUNCTION refresh_todo_stats();
```

### Django View

```python
def dashboard(request):
    stats = Todo.objects.raw("SELECT * FROM todo_stats")
    return render(request, 'todos/dashboard.html', {'stats': stats})
```

**Deliverable:** Live counts from a pre-computed view. Zero app-level caching code. No Redis.

---

## Phase 5 — Job Queue via SKIP LOCKED (Replaces SQS) (~2 hr)

**Postgres features:** `SELECT FOR UPDATE SKIP LOCKED`, `pg_notify`

This is the most underrated Postgres feature. `SKIP LOCKED` lets multiple workers pull jobs from a queue concurrently without stepping on each other — exactly what SQS does.

### How it works

1. A todo is created → a `Job` row is inserted (e.g. `send_reminder`, `mark_overdue`)
2. A worker acquires the next available job with `SKIP LOCKED` — atomic, no double-processing
3. Worker processes the job, marks it `done` or `failed`
4. `pg_notify` fires so the UI reflects the job outcome in real time

### Trigger — enqueue a job on todo creation

```sql
CREATE OR REPLACE FUNCTION enqueue_todo_job() RETURNS trigger AS $$
BEGIN
  INSERT INTO todos_job (todo_id, job_type, payload, status, created_at)
  VALUES (NEW.id, 'send_reminder', row_to_json(NEW), 'queued', NOW());
  PERFORM pg_notify('job_queue', NEW.id::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER todo_enqueue_trigger
AFTER INSERT ON todos_todo
FOR EACH ROW EXECUTE FUNCTION enqueue_todo_job();
```

### Worker — SKIP LOCKED in action

```python
# todos/worker.py

import psycopg2, time

def process_jobs():
    conn = psycopg2.connect(settings.DATABASE_URL)
    while True:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, todo_id, job_type, payload
                FROM todos_job
                WHERE status = 'queued'
                ORDER BY created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """)
            job = cur.fetchone()
            if job:
                job_id, todo_id, job_type, payload = job
                try:
                    handle_job(job_type, payload)       # your business logic
                    cur.execute(
                        "UPDATE todos_job SET status='done', processed_at=NOW() WHERE id=%s",
                        [job_id]
                    )
                except Exception:
                    cur.execute(
                        "UPDATE todos_job SET status='failed' WHERE id=%s",
                        [job_id]
                    )
                conn.commit()
        time.sleep(0.5)
```

### Run multiple workers concurrently

```bash
python manage.py run_worker &
python manage.py run_worker &
python manage.py run_worker &
```

Each worker uses `SKIP LOCKED` — they never process the same job twice. SQS behaviour, zero SQS.

### Django management command

```python
# todos/management/commands/run_worker.py
from django.core.management.base import BaseCommand
from todos.worker import process_jobs

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        process_jobs()
```

### Queue monitor view

```python
def queue_monitor(request):
    jobs = Job.objects.select_related('todo').order_by('-created_at')[:50]
    return render(request, 'todos/queue_monitor.html', {'jobs': jobs})
```

**Deliverable:** Jobs enqueued on todo creation, processed by concurrent workers with no double-processing. No SQS. No Celery.

---

## Phase 6 — MVT Wiring & Demo UI (~1 hr)

**Goal:** All views connected, clean templates, one coherent Django app.

### URL structure

```
/                → index       — todo list + create form + WebSocket live updates
/search/         → search      — FTS ranked results with highlighting
/dashboard/      → dashboard   — materialized view stats
/queue/          → queue       — job queue monitor (SKIP LOCKED workers)
/ws/todos/       → WebSocket   — Channels consumer (LISTEN/NOTIFY)
```

### Template structure

```
templates/
  base.html                  ← nav: Todos | Search | Dashboard | Queue
  todos/
    index.html               ← todo list + create form + WebSocket listener
    search_results.html      ← ranked results with highlighted terms
    dashboard.html           ← live counts from materialized view
    queue_monitor.html       ← job statuses, worker activity
```

### Demo script

1. Open `/` in two tabs → create a todo in tab A → tab B updates instantly (**LISTEN/NOTIFY**)
2. Go to `/search/?q=postgres` → ranked, highlighted results (**FTS**)
3. Go to `/dashboard/` → live counts, zero cache warming (**materialized view**)
4. Go to `/queue/` → watch jobs get picked up by concurrent workers (**SKIP LOCKED**)

**Deliverable:** One Django app. One Postgres instance. No Redis. No Elasticsearch. No SQS. No Celery.

---

## Summary

| Replaces        | Postgres feature                 | Phase | Est.        |
| --------------- | -------------------------------- | ----- | ----------- |
| —               | Project setup + models           | 1     | 1 hr        |
| Elasticsearch   | `tsvector` + GIN + `ts_headline` | 2     | 1.5 hr      |
| Redis Pub/Sub   | `pg_notify` + `LISTEN`           | 3     | 2 hr        |
| Redis cache     | Materialized view + refresh      | 4     | 1 hr        |
| SQS / job queue | `SKIP LOCKED` + `pg_notify`      | 5     | 2 hr        |
| —               | MVT wiring + demo UI             | 6     | 1 hr        |
| **Total**       |                                  |       | **~8.5 hr** |
