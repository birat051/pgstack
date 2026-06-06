# pgstack — Task Checklist

> Postgres as Redis + Elasticsearch + SQS + DB. Django MVT. Dockerized from day one.

---

## PR overview

| PR     | Phase   | Description                                     |
| ------ | ------- | ----------------------------------------------- |
| PR 01  | Phase 1 | Docker + Compose setup                          |
| PR 02  | Phase 1 | Django project scaffold                         |
| PR 03  | Phase 1 | Core models + initial migration                 |
| PR 04  | Phase 2 | FTS — GIN index + trigger                       |
| PR 05  | Phase 2 | FTS — search view + template                    |
| PR 06  | Phase 3 | LISTEN/NOTIFY — Postgres trigger + ASGI         |
| PR 07  | Phase 4 | Auth — accounts app + settings schema           |
| PR 07a | Phase 4 | Auth — signup flow (name, email, password)      |
| PR 08  | Phase 4 | Auth — Todo ownership + write permissions       |
| PR 09  | Phase 4 | Auth — user search + public/private Todo lists  |
| PR 10  | Phase 5 | LISTEN/NOTIFY — consumer + template wiring      |
| PR 11  | Phase 6 | Materialized view — migration + refresh trigger |
| PR 12  | Phase 6 | Materialized view — dashboard view + template   |
| PR 13  | Phase 7 | SKIP LOCKED — enqueue trigger                   |
| PR 14  | Phase 7 | SKIP LOCKED — worker + management command       |
| PR 15  | Phase 7 | SKIP LOCKED — queue monitor view + template     |
| PR 16  | Phase 8 | MVT wiring — base template + nav + index view   |
| PR 17  | Phase 8 | Demo polish + README                            |

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
  - [x] `django-admin startproject pgstack .` _(equivalent layout: `manage.py` + `pgstack/` package + `settings/{base,dev,prod}.py` per PROJECT_GUIDELINES)_
  - [x] Configure settings to read `DATABASE_URL` from env via `python-decouple` (`pgstack/settings/base.py`)
  - [x] Add `django.contrib.postgres` to `INSTALLED_APPS`
  - [x] Set `CHANNEL_LAYERS` to `InMemoryChannelLayer` (no Redis)
- [x] Create `todos` app
  - [x] `python manage.py startapp todos` _(equivalent: `todos/` with `apps.py`, migrations, management commands)_
  - [x] Register `todos` in `INSTALLED_APPS` (`todos.apps.TodosConfig`)
- [x] Set up ASGI entry point
  - [x] `pgstack/asgi.py` with `ProtocolTypeRouter` for `http` + `websocket`
- [x] Verify: `python manage.py check` passes
  - [x] **Local:** `.venv/bin/pip install -r requirements/dev.txt` then `.venv/bin/python manage.py check` with env from `.env.example` / `docker-compose.yml` — OK
  - [x] **Container:** `docker compose run web python manage.py check`

---

### PR 03 — Core models + initial migration

- [x] Define `Todo` model (`todos/models.py`)
  - [x] Fields: `title`, `notes`, `status` (choices), `due_date`, `created_at`
  - [x] `SearchVectorField(null=True)` for FTS (phase 2 prep)
- [x] Define `Job` model (`todos/models.py`)
  - [x] Fields: `todo` FK, `job_type`, `payload` JSONField, `status` (choices), `created_at`, `processed_at`
- [x] Run and verify migration
  - [x] `docker compose run web python manage.py makemigrations` _(no model changes; "No changes detected")_
  - [x] `docker compose run web python manage.py migrate`
  - [x] Confirm tables exist: `docker compose exec db psql -U postgres -d pgstack -c '\dt'` _(see `todos_todo`, `todos_job`)_

---

## Phase 2 — Full-text search (replaces Elasticsearch)

### PR 04 — FTS: GIN index + trigger

- [x] Write custom migration for GIN index
  - [x] `migrations.RunSQL` to `CREATE INDEX USING GIN` on `search_vector`
  - [x] Include `reverse_sql` to drop the index
- [x] Write Postgres trigger to auto-update `search_vector`
  - [x] `to_tsvector('english', coalesce(title,'') || ' ' || coalesce(notes,''))`
  - [x] Fires `BEFORE INSERT OR UPDATE` on `todos_todo`
  - [x] Apply via `RunSQL` (`0004_add_search_vector_trigger`), with `reverse_sql` to drop
- [x] Test inside Docker
  - [x] `docker compose run web python manage.py migrate`
  - [x] Insert a todo via Django shell, confirm `search_vector` is populated

---

### PR 05 — FTS: search view + template

- [x] Search view (`todos/views.py`)
  - [x] `SearchQuery` + `SearchRank` + `SearchHeadline` annotations
  - [x] Filter by `search_vector`, order by rank descending
  - [x] Wire to `GET /search/` in `todos/urls.py`
- [x] `todos/search_results.html` template
  - [x] Search bar form (`method="get"`)
  - [x] Render `headline` with `{{ todo.headline|safe }}` for highlighted terms
  - [x] Empty state message when no results
- [x] Test: `docker compose up`, visit `/search/?q=<term>`, confirm ranked results _(Docker test client: sample todo, `q=milk`, ranked results with `<b>` headlines)_

---

## Phase 3 — Live sync (replaces Redis Pub/Sub)

### PR 06 — LISTEN/NOTIFY: Postgres trigger + ASGI

- [x] Write notify trigger on `todos_todo`
  - [x] `pg_notify('todo_updates', …)` — bounded JSON payload (id, title, status, due_date, created_at, truncated `notes_preview`; fallback to id/title/status if over ~7500 bytes per `PROJECT_GUIDELINES.MD`, not raw `row_to_json(NEW)`)
  - [x] Fires `AFTER INSERT OR UPDATE`
  - [x] Apply via `RunSQL` migration with `reverse_sql` to drop (`0006_todo_notify_trigger`)
- [x] Configure Django Channels _(in `pgstack/settings/base.py`; project uses split settings, not a single `settings.py`)_
  - [x] `ASGI_APPLICATION = 'pgstack.asgi.application'`
  - [x] `CHANNEL_LAYERS` using `InMemoryChannelLayer`
- [x] Confirm `daphne` serves ASGI correctly in Docker
  - [x] `docker compose run web`: start `daphne`; logs show **Listening** on TCP; `GET /admin/login/` returns **200** via ASGI _(curl not in image; verified with Python `urllib.request`)_

---

## Phase 4 — User auth, ownership, and visibility

> Execute before LISTEN/NOTIFY consumer work so Todos are user-scoped and realtime updates do not leak across users. Per `PROJECT_GUIDELINES.MD` ("one app per domain concept"), use a separate `accounts` app for user settings and user discovery; keep Todo ownership and query rules in `todos`.

### PR 07 — Auth: accounts app + settings schema

- [x] Create `accounts` app
  - [x] `python manage.py startapp accounts`
  - [x] Register `accounts.apps.AccountsConfig` in `INSTALLED_APPS`
  - [x] Use Django's native `django.contrib.auth.models.User`; do not introduce a custom user model unless a concrete requirement appears before first production migration
- [x] Define `UserSettings` model (`accounts/models.py`)
  - [x] `user = OneToOneField(User, on_delete=CASCADE, related_name='settings')`
  - [x] `is_todo_list_private = BooleanField(default=True)`
  - [x] `created_at`, `updated_at`
  - [x] Add indexes only for fields used in `WHERE` / `ORDER BY`
- [x] Add focused migration for `UserSettings`
  - [x] One concern: create settings table only
  - [x] Verify with `docker compose run web python manage.py migrate`
- [x] Add `accounts/services.py`
  - [x] `get_or_create_user_settings(user: User) -> UserSettings`
  - [x] `set_todo_list_privacy(user: User, is_private: bool) -> None` using targeted `update()` where appropriate
  - [x] `can_view_todo_list(viewer: User | AnonymousUser, owner: User) -> bool`
- [x] Add settings view + template
  - [x] Authenticated users can view/update their Todo list privacy
  - [x] Views stay thin and delegate rules to `accounts.services`
  - [x] Wire to `GET/POST /settings/`
- [x] Tests
  - [x] Default privacy is private
  - [x] Owner can view own list regardless of privacy
  - [x] Anonymous and other users cannot view private lists
  - [x] Public lists are visible to other users

---

### PR 07a — Auth: signup flow (name, email, password)

Do this after PR 07 so signup can create `User` rows aligned with Django auth and optionally ensure `UserSettings` exists for new users (`get_or_create_user_settings`). Keep business logic out of views.

- [x] Add a signup **form** (e.g. `accounts/forms.py`) with validated fields:
  - [x] **Name** — map to `User.first_name` (and optionally `last_name`); document chosen mapping in code or a short comment
  - [x] **Email** — required, uniqueness validation against existing users
  - [x] **Password** — Django password validators (`AUTH_PASSWORD_VALIDATORS`); optionally require confirmation field for UX
- [x] Add `accounts.services.register_user(...) -> User` (or equivalent) — create user with email + hashed password + name fields; pick a deterministic **unique `username`** strategy (e.g. from normalized email plus disambiguation on collision); call `transaction.atomic` if signup also creates profile/settings rows in the same flow
- [x] Add signup **view + template**
  - [x] Thin view: instantiate form, POST delegates to service, success path logs the user in and redirects (`LOGIN_REDIRECT_URL` or `next`), or redirects to login with a message — pick one behavior and document in tests
  - [x] Wire `GET/POST` (recommended: `/auth/signup/` or `/signup/` to sit beside existing `/auth/login/`)
  - [x] Include link from **`registration/login.html`** to signup and/or login from signup template
- [x] Tests (`accounts/tests/`)
  - [x] Valid submission creates user with expected email/name and redirects or logs in
  - [x] Duplicate email yields a safe error (no user enumeration caveat optional for demo)
  - [x] Weak password fails validation messages

---

### PR 08 — Auth: Todo ownership + write permissions

- [x] Add owner relationship to `Todo`
  - [x] `owner = ForeignKey(User, on_delete=CASCADE, related_name='todos')`
  - [x] Add `select_related('owner')` where owner is rendered or checked
  - [x] Add index for `owner` + existing list ordering (`owner`, `-created_at`)
- [x] Add focused migration for `Todo.owner`
  - [x] Decide backfill for existing Todo rows before applying migration — **delete todos with no owner** (no legacy user)
  - [x] Keep schema change and data migration separated (`RunPython` after nullable `owner`, before `NOT NULL`)
  - [x] Verify with `docker compose run web python manage.py migrate`
- [x] Update Todo creation flow
  - [x] Only authenticated users can add Todo
  - [x] Use `@login_required` or `LoginRequiredMixin` on write views
  - [x] `todos.services.create_todo(...)` accepts the owner explicitly and writes it in the same create call
  - [x] Reject or redirect unauthenticated POSTs to login
- [x] Update Todo query helpers
  - [x] `todos.services.list_todos_for_user(user: User)` returns only the current user's Todos
  - [x] Todo search (`/search/?q=...`) searches the current user's Todos by default
  - [x] Shared visibility query shape is centralized instead of duplicated across views
- [x] Update downstream features that depend on Todo rows
  - [x] Dashboard counts are scoped to the authenticated user's Todos unless viewing another public user's list
  - [x] Queue monitor only shows jobs for the authenticated user's Todos
  - [x] LISTEN/NOTIFY consumers do not leak private Todo data across users
- [x] Tests
  - [x] Anonymous users cannot create Todos
  - [x] Authenticated users create Todos owned by themselves
  - [x] User A cannot see User B's private Todos in index, search, dashboard, queue, or live updates
  - [x] User A can still see their own Todos

---

### PR 09 — Auth: user search + public/private Todo lists

- [x] User search feature (`accounts/views.py`, `accounts/services.py`)
  - [x] Search Django `User` by username only for now
  - [x] Use case-insensitive prefix/contains matching with a small limit (e.g. 20)
  - [x] Keep search logic in `accounts.services.search_users_by_username(query: str)`
  - [x] Wire to `GET /users/search/?q=<username>`
- [x] User search template
  - [x] Search bar form (`method="get"`)
  - [x] Render username and link to public Todo list route
  - [x] Empty state for no matching users
- [x] Public/private Todo list view
  - [x] Route: `GET /users/<username>/todos/`
  - [x] Owner always sees their own list
  - [x] Other authenticated users can view only if `UserSettings.is_todo_list_private = False`
  - [x] Anonymous users can view public lists only if product decision allows it; otherwise redirect to login before evaluating visibility
  - [x] Private lists return 404 or 403 consistently (choose one and test it)
- [x] Update Todo search behavior for viewed users
  - [x] Current user's `/search/` remains own-list search
  - [x] Optional owner-specific search (`/users/<username>/todos/?q=<term>`) respects the same privacy rules
- [x] Tests
  - [x] Username search finds expected users and limits noise
  - [x] Username search does not expose private Todo content
  - [x] Public user Todo list is visible according to the chosen anonymous/authenticated policy
  - [x] Private user Todo list is blocked for other users
  - [x] Owner-specific Todo search respects privacy

---

## Phase 5 — Live sync (consumer wiring)

### PR 10 — LISTEN/NOTIFY: consumer + template wiring

- [x] `TodoConsumer` (`todos/consumers.py`)
  - [x] `connect()`: accept + launch `asyncpg` LISTEN coroutine
  - [x] `on_notify()`: forward JSON payload to WebSocket client
  - [x] `disconnect()`: cancel listener, close `asyncpg` connection
- [x] WebSocket routing (`todos/routing.py`)
  - [x] `URLRouter` for `ws/todos/`
  - [x] Wire into `pgstack/asgi.py` `ProtocolTypeRouter`
- [x] `todos/index.html` WebSocket client
  - [x] Inline script: `new WebSocket('ws://.../ws/todos/')`
  - [x] `onmessage`: prepend or update todo row in DOM without page reload
- [x] Test: open two browser tabs at `/`, create a todo in tab A, confirm it appears in tab B _(Docker smoke: logged-in WebSocket on `/ws/todos/` received NOTIFY after POST create on `/`)_

---

## Phase 6 — Dashboard cache (replaces Redis cache)

### PR 11 — Materialized view: migration + refresh trigger

- [x] Create `todo_stats` materialized view via `RunSQL` migration
  - [x] `GROUP BY status`: columns `total`, `overdue_count`, `done_count`
  - [x] `CREATE UNIQUE INDEX ON todo_stats(status)`
  - [x] Include `reverse_sql` to drop view + index
- [x] Write refresh trigger on `todos_todo`
  - [x] `REFRESH MATERIALIZED VIEW CONCURRENTLY todo_stats`
  - [x] Fires `AFTER INSERT OR UPDATE OR DELETE`
  - [x] Apply via `RunSQL` migration
- [x] Smoke test
  - [x] Insert a todo, query `todo_stats` directly, confirm counts updated

---

### PR 12 — Materialized view: dashboard view + template

- [x] Dashboard view (`todos/views.py`)
  - [x] Raw query: `SELECT * FROM todo_stats`
  - [x] Wire to `GET /dashboard/` in `todos/urls.py`
- [x] `todos/dashboard.html` template
  - [x] Status count cards: pending, done, overdue
  - [x] No loading state — reads are sub-millisecond
- [x] Test: `docker compose up`, visit `/dashboard/`, confirm live counts

---

## Phase 7 — Job queue (replaces SQS)

### PR 13 — SKIP LOCKED: enqueue trigger

- [x] Write enqueue trigger on `todos_todo` INSERT
  - [x] `INSERT INTO todos_job` with `status='queued'`
  - [x] `pg_notify('job_queue', NEW.id::text)`
  - [x] Apply via `RunSQL` migration with `reverse_sql` to drop
- [x] Verify
  - [x] Create a todo via the app, confirm a `Job` row appears with `status=queued`

---

### PR 14 — SKIP LOCKED: worker + management command

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

### PR 15 — SKIP LOCKED: queue monitor view + template

- [ ] Queue monitor view (`todos/views.py`)
  - [ ] Latest 50 jobs, `select_related('todo')`
  - [ ] Wire to `GET /queue/` in `todos/urls.py`
- [ ] `todos/queue_monitor.html` template
  - [ ] Table: `job_type`, todo title, status badge, `processed_at`
  - [ ] Status badges: queued (gray), processing (amber), done (green), failed (red)
- [ ] Test: `docker compose up --scale worker=3`, visit `/queue/`, watch jobs move through statuses

---

## Phase 8 — MVT wiring + polish

### PR 16 — MVT wiring: base template + nav + index view

- [ ] `base.html`
  - [ ] Nav: Todos | Search | Users | Dashboard | Queue | Settings
  - [ ] Show Login/Register/Logout links based on authentication state
  - [ ] `{% block content %}` placeholder
  - [ ] All other templates extend `base.html`
- [ ] Index view + template
  - [ ] Authenticated users see their own Todos ordered by `created_at` descending
  - [ ] Inline create form (POST) is visible only to authenticated users
  - [ ] WebSocket listener script only applies updates visible to the current user
- [ ] Wire all URLs
  - [ ] `todos/urls.py`: `/`, `/search/`, `/dashboard/`, `/queue/`
  - [ ] `accounts/urls.py`: `/settings/`, signup URL (per PR 07a), `/users/search/`, `/users/<username>/todos/`
  - [ ] Include in `pgstack/urls.py`
- [ ] Test: full app navigation works end to end in Docker

---

### PR 17 — Demo polish + README

- [ ] `README.md`
  - [ ] What pgstack is + the four things Postgres replaces
  - [ ] Prerequisites: Docker + Docker Compose only
  - [ ] Setup: `docker compose up`
  - [ ] Demo script (auth + 4 Postgres feature steps)
  - [ ] Explain that Todos are user-owned and Todo lists are private by default
- [ ] Demo smoke test (run entirely via `docker compose up`)
  - [ ] Register/login as two users
  - [ ] User A creates private Todos; User B cannot view them
  - [ ] User A makes Todo list public; User B can find User A by username and view the public list
  - [ ] Two tabs: create todo in tab A → appears in tab B (LISTEN/NOTIFY)
  - [ ] `/search/` returns ranked highlighted results for the authenticated user's visible Todo set (FTS)
  - [ ] `/dashboard/` shows live counts scoped to the authenticated user or viewed public user (materialized view)
  - [ ] `/queue/` shows jobs processed by concurrent workers without leaking other users' private Todos (SKIP LOCKED)
- [ ] Final check: `docker compose down -v && docker compose up --build` from scratch, all features work

---

## What Postgres replaces

| Replaces        | Postgres feature                       | Phase |
| --------------- | -------------------------------------- | ----- |
| Elasticsearch   | `tsvector` + GIN index + `ts_headline` | 2     |
| Redis Pub/Sub   | `pg_notify` + `LISTEN`                 | 3     |
| Redis cache     | Materialized view + concurrent refresh | 4     |
| SQS / job queue | `SELECT FOR UPDATE SKIP LOCKED`        | 5     |
