# pgstack — Task Checklist

> Postgres as Redis + Elasticsearch + SQS + DB. Django MVT. Dockerized from day one.

---

## PR overview

| PR    | Phase   | Description                                     |
| ----- | ------- | ----------------------------------------------- |
| PR 01 | Phase 1 | Docker + Compose setup                          |
| PR 02 | Phase 1 | Django project scaffold                         |
| PR 03 | Phase 1 | Core models + initial migration                 |
| PR 04 | Phase 2 | FTS — GIN index + trigger                       |
| PR 05 | Phase 2 | FTS — search view + template                    |
| PR 06 | Phase 3 | LISTEN/NOTIFY — Postgres trigger + ASGI         |
| PR 07 | Phase 3 | LISTEN/NOTIFY — consumer + template wiring      |
| PR 08 | Phase 4 | Materialized view — migration + refresh trigger |
| PR 09 | Phase 4 | Materialized view — dashboard view + template   |
| PR 10 | Phase 5 | SKIP LOCKED — enqueue trigger                   |
| PR 11 | Phase 5 | SKIP LOCKED — worker + management command       |
| PR 12 | Phase 5 | SKIP LOCKED — queue monitor view + template     |
| PR 13 | Phase 6 | MVT wiring — base template + nav + index view   |
| PR 14 | Phase 6 | Demo polish + README                            |

---

## Phase 1 — Project setup

### PR 01 — Docker + Compose setup

> Everything runs in Docker from the first commit. No local Postgres, no local Python env required.

- [x] Create `Dockerfile`
  - [x] Base image: `python:3.12-slim-bookworm` (3.12 slim)
  - [x] Set `WORKDIR /app`
  - [x] Copy `requirements/`, run `pip install --no-cache-dir -r requirements/${ENV}.txt` (default `prod` per PROJECT_GUIDELINES)
  - [x] Copy project source
  - [x] Expose port `8000`
  - [x] CMD: `wait_for_db` → `migrate` → `daphne -b 0.0.0.0 -p 8000 pgstack.asgi:application` (PROJECT_GUIDELINES)
- [x] Create `docker-compose.yml`
  - [x] `db` service: `postgres:16`, named volume, env vars (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`)
  - [x] `web` service: build from `Dockerfile`, depends_on `db`, mounts source as volume for live reload
  - [x] `worker` service: same image as `web`, command: `python manage.py run_worker`
  - [x] Shared `environment` block pointing `DATABASE_URL` at `db` service
- [x] Create `.env.example` with all required env vars
- [x] Create `.dockerignore` (exclude `__pycache__`, `.git`, `*.pyc`)
- [x] Create `requirements.txt`
  - [x] `django`, `psycopg2-binary`, `channels`, `daphne`, `asyncpg`, `python-decouple` (via `requirements/base.txt`; root file is `-r requirements/base.txt`)
- [ ] Smoke test: `docker compose up` starts without errors, db is reachable

---

### PR 02 — Django project scaffold

- [x] Initialise Django project inside container
  - [x] `django-admin startproject pgstack .` *(equivalent layout: `manage.py` + `pgstack/` package + `settings/{base,dev,prod}.py` per PROJECT_GUIDELINES)*
  - [x] Configure settings to read `DATABASE_URL` from env via `python-decouple` (`pgstack/settings/base.py`)
  - [x] Add `django.contrib.postgres` to `INSTALLED_APPS`
  - [x] Set `CHANNEL_LAYERS` to `InMemoryChannelLayer` (no Redis)
- [x] Create `todos` app
  - [x] `python manage.py startapp todos` *(equivalent: `todos/` with `apps.py`, migrations, management commands)*
  - [x] Register `todos` in `INSTALLED_APPS` (`todos.apps.TodosConfig`)
- [x] Set up ASGI entry point
  - [x] `pgstack/asgi.py` with `ProtocolTypeRouter` for `http` + `websocket`
- [x] Verify: `python manage.py check` passes
  - [x] **Local:** `.venv/bin/pip install -r requirements/dev.txt` then `.venv/bin/python manage.py check` with env from `.env.example` / `docker-compose.yml` — OK
  - [x] **Container:** `docker compose run web python manage.py check`

---

### PR 03 — Core models + initial migration

- [ ] Define `Todo` model (`todos/models.py`)
  - [ ] Fields: `title`, `notes`, `status` (choices), `due_date`, `created_at`
  - [ ] `SearchVectorField(null=True)` for FTS (phase 2 prep)
- [ ] Define `Job` model (`todos/models.py`)
  - [ ] Fields: `todo` FK, `job_type`, `payload` JSONField, `status` (choices), `created_at`, `processed_at`
- [ ] Run and verify migration
  - [ ] `docker compose run web python manage.py makemigrations`
  - [ ] `docker compose run web python manage.py migrate`
  - [ ] Confirm tables exist: `docker compose exec db psql -U postgres -c '\dt'`

---

## Phase 2 — Full-text search (replaces Elasticsearch)

### PR 04 — FTS: GIN index + trigger

- [ ] Write custom migration for GIN index
  - [ ] `migrations.RunSQL` to `CREATE INDEX USING GIN` on `search_vector`
  - [ ] Include `reverse_sql` to drop the index
- [ ] Write Postgres trigger to auto-update `search_vector`
  - [ ] `to_tsvector('english', coalesce(title,'') || ' ' || coalesce(notes,''))`
  - [ ] Fires `BEFORE INSERT OR UPDATE` on `todos_todo`
  - [ ] Apply via `RunSQL` in the same migration, with `reverse_sql` to drop
- [ ] Test inside Docker
  - [ ] `docker compose run web python manage.py migrate`
  - [ ] Insert a todo via Django shell, confirm `search_vector` is populated

---

### PR 05 — FTS: search view + template

- [ ] Search view (`todos/views.py`)
  - [ ] `SearchQuery` + `SearchRank` + `SearchHeadline` annotations
  - [ ] Filter by `search_vector`, order by rank descending
  - [ ] Wire to `GET /search/` in `todos/urls.py`
- [ ] `todos/search_results.html` template
  - [ ] Search bar form (`method="get"`)
  - [ ] Render `headline` with `{{ todo.headline|safe }}` for highlighted terms
  - [ ] Empty state message when no results
- [ ] Test: `docker compose up`, visit `/search/?q=<term>`, confirm ranked results

---

## Phase 3 — Live sync (replaces Redis Pub/Sub)

### PR 06 — LISTEN/NOTIFY: Postgres trigger + ASGI

- [ ] Write notify trigger on `todos_todo`
  - [ ] `pg_notify('todo_updates', row_to_json(NEW)::text)`
  - [ ] Fires `AFTER INSERT OR UPDATE`
  - [ ] Apply via `RunSQL` migration with `reverse_sql` to drop
- [ ] Configure Django Channels in `settings.py`
  - [ ] `ASGI_APPLICATION = 'pgstack.asgi.application'`
  - [ ] `CHANNEL_LAYERS` using `InMemoryChannelLayer`
- [ ] Confirm `daphne` serves ASGI correctly in Docker
  - [ ] `docker compose up`, check logs for daphne startup

---

### PR 07 — LISTEN/NOTIFY: consumer + template wiring

- [ ] `TodoConsumer` (`todos/consumers.py`)
  - [ ] `connect()`: accept + launch `asyncpg` LISTEN coroutine
  - [ ] `on_notify()`: forward JSON payload to WebSocket client
  - [ ] `disconnect()`: cancel listener, close `asyncpg` connection
- [ ] WebSocket routing (`todos/routing.py`)
  - [ ] `URLRouter` for `ws/todos/`
  - [ ] Wire into `pgstack/asgi.py` `ProtocolTypeRouter`
- [ ] `todos/index.html` WebSocket client
  - [ ] Inline script: `new WebSocket('ws://.../ws/todos/')`
  - [ ] `onmessage`: prepend or update todo row in DOM without page reload
- [ ] Test: open two browser tabs at `/`, create a todo in tab A, confirm it appears in tab B

---

## Phase 4 — Dashboard cache (replaces Redis cache)

### PR 08 — Materialized view: migration + refresh trigger

- [ ] Create `todo_stats` materialized view via `RunSQL` migration
  - [ ] `GROUP BY status`: columns `total`, `overdue_count`, `done_count`
  - [ ] `CREATE UNIQUE INDEX ON todo_stats(status)`
  - [ ] Include `reverse_sql` to drop view + index
- [ ] Write refresh trigger on `todos_todo`
  - [ ] `REFRESH MATERIALIZED VIEW CONCURRENTLY todo_stats`
  - [ ] Fires `AFTER INSERT OR UPDATE OR DELETE`
  - [ ] Apply via `RunSQL` migration
- [ ] Smoke test
  - [ ] Insert a todo, query `todo_stats` directly, confirm counts updated

---

### PR 09 — Materialized view: dashboard view + template

- [ ] Dashboard view (`todos/views.py`)
  - [ ] Raw query: `SELECT * FROM todo_stats`
  - [ ] Wire to `GET /dashboard/` in `todos/urls.py`
- [ ] `todos/dashboard.html` template
  - [ ] Status count cards: pending, done, overdue
  - [ ] No loading state — reads are sub-millisecond
- [ ] Test: `docker compose up`, visit `/dashboard/`, confirm live counts

---

## Phase 5 — Job queue (replaces SQS)

### PR 10 — SKIP LOCKED: enqueue trigger

- [ ] Write enqueue trigger on `todos_todo` INSERT
  - [ ] `INSERT INTO todos_job` with `status='queued'`
  - [ ] `pg_notify('job_queue', NEW.id::text)`
  - [ ] Apply via `RunSQL` migration with `reverse_sql` to drop
- [ ] Verify
  - [ ] Create a todo via the app, confirm a `Job` row appears with `status=queued`

---

### PR 11 — SKIP LOCKED: worker + management command

- [ ] Worker function (`todos/worker.py`)
  - [ ] `SELECT … FOR UPDATE SKIP LOCKED LIMIT 1`
  - [ ] `handle_job()` dispatcher switching on `job_type`
  - [ ] `UPDATE` status to `done` or `failed` + set `processed_at`
  - [ ] Sleep `0.5s` between polls
- [ ] `run_worker` management command
  - [ ] `todos/management/commands/run_worker.py`
  - [ ] Calls `process_jobs()` in a loop
- [ ] Confirm `worker` service in `docker-compose.yml` runs the command
  - [ ] `command: python manage.py run_worker`
- [ ] Concurrency test
  - [ ] Scale worker to 3: `docker compose up --scale worker=3`
  - [ ] Create 10 todos, confirm no job is processed twice

---

### PR 12 — SKIP LOCKED: queue monitor view + template

- [ ] Queue monitor view (`todos/views.py`)
  - [ ] Latest 50 jobs, `select_related('todo')`
  - [ ] Wire to `GET /queue/` in `todos/urls.py`
- [ ] `todos/queue_monitor.html` template
  - [ ] Table: `job_type`, todo title, status badge, `processed_at`
  - [ ] Status badges: queued (gray), processing (amber), done (green), failed (red)
- [ ] Test: `docker compose up --scale worker=3`, visit `/queue/`, watch jobs move through statuses

---

## Phase 6 — MVT wiring + polish

### PR 13 — MVT wiring: base template + nav + index view

- [ ] `base.html`
  - [ ] Nav: Todos | Search | Dashboard | Queue
  - [ ] `{% block content %}` placeholder
  - [ ] All other templates extend `base.html`
- [ ] Index view + template
  - [ ] List all todos ordered by `created_at` descending
  - [ ] Inline create form (POST)
  - [ ] WebSocket listener script included
- [ ] Wire all URLs
  - [ ] `todos/urls.py`: `/`, `/search/`, `/dashboard/`, `/queue/`
  - [ ] Include in `pgstack/urls.py`
- [ ] Test: full app navigation works end to end in Docker

---

### PR 14 — Demo polish + README

- [ ] `README.md`
  - [ ] What pgstack is + the four things Postgres replaces
  - [ ] Prerequisites: Docker + Docker Compose only
  - [ ] Setup: `docker compose up`
  - [ ] Demo script (4 steps)
- [ ] Demo smoke test (run entirely via `docker compose up`)
  - [ ] Two tabs: create todo in tab A → appears in tab B (LISTEN/NOTIFY)
  - [ ] `/search/` returns ranked highlighted results (FTS)
  - [ ] `/dashboard/` shows live counts (materialized view)
  - [ ] `/queue/` shows jobs processed by concurrent workers (SKIP LOCKED)
- [ ] Final check: `docker compose down -v && docker compose up --build` from scratch, all features work

---

## What Postgres replaces

| Replaces        | Postgres feature                       | Phase |
| --------------- | -------------------------------------- | ----- |
| Elasticsearch   | `tsvector` + GIN index + `ts_headline` | 2     |
| Redis Pub/Sub   | `pg_notify` + `LISTEN`                 | 3     |
| Redis cache     | Materialized view + concurrent refresh | 4     |
| SQS / job queue | `SELECT FOR UPDATE SKIP LOCKED`        | 5     |
