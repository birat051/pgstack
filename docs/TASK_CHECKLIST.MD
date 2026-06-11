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
| PR 18  | Phase 9 | Design — CSS tokens + badge system + static setup |
| PR 19  | Phase 9 | Design — base.html redesign + partials          |
| PR 20  | Phase 9 | Design — Landing + Index page                   |
| PR 21  | Phase 9 | Design — Auth pages (login + signup)            |
| PR 22  | Phase 9 | Design — Dashboard + Queue monitor              |
| PR 23  | Phase 9 | Design — Search + Users pages                   |
| PR 24  | Phase 9 | Design — Settings + system states               |

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

- [x] Worker function (`todos/worker.py`)
  - [x] `SELECT … FOR UPDATE SKIP LOCKED LIMIT 1`
  - [x] `handle_job()` dispatcher switching on `job_type`
  - [x] `UPDATE` status to `done` or `failed` + set `processed_at`
  - [x] Sleep `0.5s` between polls
- [x] `run_worker` management command
  - [x] `todos/management/commands/run_worker.py`
  - [x] Calls `process_jobs()` in a loop
- [x] Confirm `worker` service in `docker-compose.yml` runs the command
  - [x] `command: python manage.py run_worker`
- [x] Concurrency test
  - [x] Scale worker to 3: `docker compose up --scale worker=3`
  - [x] Create 10 todos, confirm no job is processed twice

---

### PR 15 — SKIP LOCKED: queue monitor view + template

- [x] Queue monitor view (`todos/views.py`)
  - [x] Latest 50 jobs, `select_related('todo')`
  - [x] Wire to `GET /queue/` in `todos/urls.py`
- [x] `todos/queue_monitor.html` template
  - [x] Table: `job_type`, todo title, status badge, `processed_at`
  - [x] Status badges: queued (gray), processing (amber), done (green), failed (red)
- [x] Test: `docker compose up --scale worker=3`, visit `/queue/`, watch jobs move through statuses

---

## Phase 8 — MVT wiring + polish

### PR 16 — MVT wiring: base template + nav + index view

- [x] `base.html`
  - [x] Nav: Todos | Search | Users | Dashboard | Queue | Settings
  - [x] Show Login/Register/Logout links based on authentication state
  - [x] `{% block content %}` placeholder
  - [x] All other templates extend `base.html`
- [x] Index view + template
  - [x] Authenticated users see their own Todos ordered by `created_at` descending
  - [x] Inline create form (POST) is visible only to authenticated users
  - [x] WebSocket listener script only applies updates visible to the current user
- [x] Wire all URLs
  - [x] `todos/urls.py`: `/`, `/search/`, `/dashboard/`, `/queue/`
  - [x] `accounts/urls.py`: `/settings/`, signup URL (per PR 07a), `/users/search/`, `/users/<username>/todos/`
  - [x] Include in `pgstack/urls.py`
- [x] Test: full app navigation works end to end in Docker

---

### PR 17 — Demo polish + README

- [x] `README.md`
  - [x] What pgstack is + the four things Postgres replaces
  - [x] Prerequisites: Docker + Docker Compose only
  - [x] Setup: `docker compose up`
  - [x] Demo script (auth + 4 Postgres feature steps)
  - [x] Explain that Todos are user-owned and Todo lists are private by default
- [x] Demo smoke test (run entirely via `docker compose up`)
  - [x] Register/login as two users
  - [x] User A creates private Todos; User B cannot view them
  - [x] User A makes Todo list public; User B can find User A by username and view the public list
  - [x] Two tabs: create todo in tab A → appears in tab B (LISTEN/NOTIFY)
  - [x] `/search/` returns ranked highlighted results for the authenticated user's visible Todo set (FTS)
  - [x] `/dashboard/` shows live counts scoped to the authenticated user or viewed public user (materialized view)
  - [x] `/queue/` shows jobs processed by concurrent workers without leaking other users' private Todos (SKIP LOCKED)
- [x] Final check: `docker compose down -v && docker compose up --build` from scratch, all features work

---

## Phase 9 — Design system implementation

> Apply the design system from `design/` to every Django template. No React, no build step — plain server-rendered HTML extending `base.html` with CSS custom properties from `static/css/base.css`. Source of truth for every visual detail is `design/Design System.html` and `design/Implementation Handoff.html`.

### PR 18 — Design: CSS tokens + badge system + static setup

> Foundation layer. Everything else in Phase 9 depends on this landing first.

- [ ] Create `static/css/base.css`
  - [ ] `:root` block with all 18 light-mode tokens (`--bg`, `--bg-2`, `--paper`, `--ink`, `--ink-2`, `--muted`, `--rule`, `--rule-2`, `--pg`, `--pg-deep`, `--pg-soft`, `--green`, `--amber`, `--red`, `--sans`, `--mono`, `--serif`)
  - [ ] Shadow variables: `--shadow-sm`, `--shadow-md`, `--shadow-card`, `--focus-ring`
  - [ ] Radius variables: `--radius-xs` (4px) through `--radius-2xl` (16px) and `--radius-pill` (999px)
  - [ ] Dark mode block: `[data-theme="dark"]` overrides for all surface/ink/accent tokens (see `design/Design System.html` §Dark mode tokens and `design/Implementation Handoff.html` §01)
  - [ ] Global reset: `*, *::before, *::after { box-sizing: border-box; }`, body font/color/background wired to tokens
  - [ ] `@keyframes pulse-dot { 0%,100% { opacity:1 } 50% { opacity:.35 } }` for processing badge dot
  - [ ] Google Fonts `<link>` tags for Geist (400/500/600/700), Geist Mono (400/500/600), Instrument Serif italic — added to `base.html` `<head>`, not the CSS file
- [ ] Create `static/css/badges.css`
  - [ ] `.badge` base: `inline-flex`, `border-radius: 999px`, Geist Mono 11.5px (0.719rem), `letter-spacing: 0.04em`
  - [ ] `.badge::before` dot: 7×7 px circle, `background: currentColor`
  - [ ] `.badge--pending`: bg `var(--bg-2)`, border `var(--rule-2)`, color `var(--muted)`
  - [ ] `.badge--done`: bg `rgba(61,122,74,.10)`, border `rgba(61,122,74,.28)`, color `var(--green)`
  - [ ] `.badge--overdue`: bg `rgba(177,75,60,.09)`, border `rgba(177,75,60,.28)`, color `var(--red)`
  - [ ] `.badge--queued`: same visual as `--pending`
  - [ ] `.badge--processing`: bg `rgba(185,125,42,.10)`, border `rgba(185,125,42,.30)`, color `var(--amber)`; `::before` uses `pulse-dot` animation
  - [ ] `.badge--failed`: same visual as `--overdue`
- [ ] Create `static/css/forms.css`
  - [ ] `.field` wrapper, `.field__label` (Geist Mono, 11px, uppercase, 0.10em letter-spacing, `var(--muted)`)
  - [ ] Input base: height 42px, padding `0 12px`, border `1px solid var(--rule-2)`, radius `var(--radius-md)`, bg `#fff`
  - [ ] `:focus` state: border `var(--pg)`, `box-shadow: var(--focus-ring)`
  - [ ] `.field--error` input: border `var(--red)`, `box-shadow: 0 0 0 3px rgba(177,75,60,.12)`
  - [ ] `.field__error` message: Geist Mono 11.5px, `var(--red)`, leading `⚠` symbol
  - [ ] `.msg-banner` base + modifiers `--success`, `--info`, `--warning`, `--error` with left-border accent, icon background (per `design/Implementation Handoff.html` §07)
  - [ ] `.search-result__snippet b` highlight: bg `#fef3c7`, color `#7c4500`, padding `0 2px`, radius 3px
- [ ] Configure Django static files
  - [ ] Add `django.contrib.staticfiles` to `INSTALLED_APPS` (verify it's present)
  - [ ] Set `STATICFILES_DIRS = [BASE_DIR / "static"]` in `pgstack/settings/base.py`
  - [ ] Add `{% load static %}` and `{% static 'css/base.css' %}` link to `base.html`
  - [ ] Verify: `docker compose run web python manage.py collectstatic --noinput` succeeds
- [ ] Add `app_name` to every `urls.py` that needs active-nav detection
  - [ ] `todos/urls.py` → `app_name = 'todos'`
  - [ ] `accounts/urls.py` → `app_name = 'accounts'`
  - [ ] Update `pgstack/urls.py` `include()` calls to use namespaced includes (`namespace='todos'`, `namespace='accounts'`) where needed

---

### PR 19 — Design: base.html redesign + template partials

> Every template extends this shell. Get it right before touching individual pages.

- [ ] Rewrite `todos/templates/todos/base.html` to match `design/Implementation Handoff.html` §04 nav HTML spec
  - [ ] `<html lang="en">` with `{% load static %}` at top
  - [ ] `<head>`: charset, viewport, `{% block title %}pgstack{% endblock %}`, Google Fonts `<link>` preconnect + font stylesheet, `<link rel="stylesheet" href="{% static 'css/base.css' %}">`, badge + form CSS links, `{% block extra_head %}{% endblock %}`
  - [ ] `<nav class="site-nav" aria-label="Main navigation">` with inner `site-nav__inner` div
  - [ ] Wordmark: `.site-nav__brand` → `.brand-mark` (28×28 px ink square, "pg") + `.brand-name` ("pgstack") + `.brand-version` ("v0.1" pill)
  - [ ] Nav links: `<ul class="site-nav__links" role="list">` — Todos, Search, Users, Dashboard, Queue, Settings
    - [ ] Active detection via `{% with app=request.resolver_match.app_name %}` — add `is-active` class when app matches (Todos→`todos`, Search→`todos` search view namespace, Users→`accounts`, Dashboard→`todos`, Queue→`todos`, Settings→`accounts`)
    - [ ] Active link indicator: 2px blue underbar (`var(--pg)`) via `::after` pseudo-element, positioned at `bottom: -1px`
  - [ ] Auth area: `{% if user.is_authenticated %}` → avatar initials (`.site-nav__avatar` using `{{ user.username|slice:":2"|upper }}`), username, divider, logout POST form with CSRF; else → "Log in" ghost link + "Register" primary btn
  - [ ] Django messages block: `{% if messages %}` → `<div class="messages-container" role="status" aria-live="polite">` with `{% for message in messages %}` → `<div class="msg-banner msg-banner--{{ message.tags }}">` pattern
  - [ ] `<main class="page-content">{% block content %}{% endblock %}</main>`
  - [ ] `{% block extra_js %}{% endblock %}` before `</body>`
  - [ ] Add `site-nav` CSS to `base.css`: nav height 56px, `var(--paper)` bg, `box-shadow: 0 1px 0 rgba(20,24,29,.02), 0 2px 8px rgba(20,24,29,.05)`, inner `max-width: 1280px`, `padding: 0 28px`
  - [ ] Add `site-nav__link` and `is-active` styles (Geist Mono 12.5px, height 36px, padding `0 12px`, radius 8px; active: bg `var(--bg-2)`, border `var(--rule)`, font-weight 500)
  - [ ] Add `.page-content` max-width 1280px, `margin: 0 auto`, `padding: 32px 28px`
- [ ] Create `todos/templates/todos/partials/badge.html`
  - [ ] `<span class="badge badge--{{ status|lower }}">{{ status }}</span>`
  - [ ] Document include usage: `{% include 'todos/partials/badge.html' with status=todo.status %}`
- [ ] Create `todos/templates/todos/partials/form_field.html`
  - [ ] Renders `.field`, `.field__label`, `{{ field }}`, `{% for error in field.errors %}` → `.field__error` with `⚠` prefix
  - [ ] Applies `field--error` class to wrapper when `field.errors` is non-empty
- [ ] Create `todos/templates/todos/partials/non_field_errors.html`
  - [ ] `{% if form.non_field_errors %}` → `.msg-banner.msg-banner--error` banner with `<ul>` list of errors
- [ ] Verify: every existing template still renders (`docker compose up`, visit all routes, no 500s)

---

### PR 20 — Design: Landing + Index page

> Two views of the home route: logged-out landing gate and the authenticated todo list.

- [ ] **Logged-out landing gate** (`todos/templates/todos/index.html` or a dedicated `landing.html`)
  - [ ] Centered layout: `pg` logo mark (52×52 px), kicker label "pgstack · demo app", `h2` "Sign in to continue"
  - [ ] Subtext paragraph explaining the four Postgres features (max-width ~340px, `var(--muted)`)
  - [ ] CTA buttons: "Log in" (secondary border style) + "Register" (primary `var(--ink)` bg)
  - [ ] Auth note info callout: left `var(--pg)` border, blue soft bg, Geist Mono 12px — "Login and registration are handled by `django.contrib.auth`. Sessions stored in Postgres."
  - [ ] This is purely server-rendered; no JS
- [ ] **Authenticated todo list** (`todos/templates/todos/index.html`)
  - [ ] Page header row: left side has kicker label ("Phase 1 · django.contrib.auth") + `<h1>Todos</h1>` (34px, weight 600, letter-spacing −0.025em); right side has filter input field (42px height, search icon SVG) + "+ New todo" primary button
  - [ ] Header separated from content with `border-bottom: 1px solid var(--rule)`, `padding-bottom: 20px`, `margin-bottom: 28px`
  - [ ] **Status filter tab row**: All | Pending | Done | Overdue — pill-style tabs (height 32px, Geist Mono 12px), active tab has bg `var(--paper)`, border `var(--rule)`, shadow-sm; inactive is transparent with `var(--muted)` text; colored dots for Pending/Done/Overdue tabs
  - [ ] **Todo rows**: `<ul id="todo-list">` with list items — each row is `<li class="todo-row">` with: checkbox (18×18 px, radius 5px, ink-filled when done), title text (14.5px sans), due-date label (Geist Mono 11px `var(--muted)`), status badge via partial include
  - [ ] Done todos: title `line-through`, `textDecorationColor: var(--rule-2)`, color `var(--muted)`
  - [ ] Row styles: bg `var(--paper)`, border `var(--rule)`, radius 10px, `shadow-sm`, `padding: 13px 16px`, `display: flex`, `align-items: center`, `gap: 14px`
  - [ ] **Empty state** (no todos): dashed border container (radius 14px, bg `var(--bg)`), circle icon `○`, heading "No todos yet", subtext about LISTEN trigger, "+ New todo" button
  - [ ] **Inline create form**: `<form method="post">` at top of content area — title input + optional notes textarea + "Save todo" primary button; only shown to `{% if user.is_authenticated %}`
  - [ ] **WebSocket script** in `{% block extra_js %}`: vanilla JS, ~20 lines, opens `wss?://host/ws/todos/`, on message builds `<li class="todo-row todo-row--new">` and calls `list.insertAdjacentHTML('afterbegin', html)` (per `design/Implementation Handoff.html` §08 WebSocket snippet)
  - [ ] Add `.todo-row`, `.todo-row--new` (brief highlight animation or ring), `.todo-row__title` CSS to `base.css`

---

### PR 21 — Design: Auth pages (login + signup)

> Centered card layout, Geist Mono labels, design system form inputs.

- [ ] **Login page** (`accounts/templates/registration/login.html`)
  - [ ] Full-page centered layout: `display: flex; align-items: center; justify-content: center; min-height: calc(100vh - 56px)` (accounts for nav height)
  - [ ] Auth card: bg `var(--paper)`, border `var(--rule-2)`, radius `var(--radius-2xl)` (16px), padding 32px, max-width 400px, shadow-card
  - [ ] Card header: `pg` logo mark (40×40 px), kicker "pgstack · login", `<h2>` "Welcome back" (24px, weight 600)
  - [ ] Form fields using `.field` / `.field__label` / `.field__error` pattern from `partials/form_field.html`
  - [ ] "Log in" primary button (full width, height 44px)
  - [ ] Link to signup: "No account? Register →" (Geist Mono 12.5px, `var(--muted)`, centered below button)
  - [ ] Non-field errors via `partials/non_field_errors.html`
- [ ] **Signup page** (`accounts/templates/accounts/signup.html`)
  - [ ] Same centered card layout as login
  - [ ] Card header: kicker "pgstack · register", `<h2>` "Create an account"
  - [ ] Fields: Name (maps to `first_name`), Email, Password, Password confirmation — rendered via `partials/form_field.html`
  - [ ] "Create account" primary button (full width, height 44px)
  - [ ] Link to login: "Already have an account? Log in →"
  - [ ] Auth note info callout at bottom of card: `django.contrib.auth` + `UserSettings` created on register (matches `design/Auth Pages.html` detail)
  - [ ] Non-field errors via `partials/non_field_errors.html`
- [ ] Verify field widget attrs are set in `accounts/forms.py`
  - [ ] Each field's widget has `class="field__input"` (or equivalent) + appropriate `placeholder` attr
  - [ ] Password fields use `PasswordInput` widget

---

### PR 22 — Design: Dashboard + Queue monitor

> Stats from the materialized view and job table presented with the full design system.

- [ ] **Dashboard page** (`todos/templates/todos/dashboard.html`)
  - [ ] Page header: kicker "Phase 6 · Materialized view + REFRESH CONCURRENTLY", `<h1>Dashboard</h1>`
  - [ ] **Stat cards row** (3 cards, equal width, `display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px`):
    - [ ] Each card: bg `var(--paper)`, border `var(--rule-2)`, radius `var(--radius-xl)` (14px), padding 24px, shadow-card
    - [ ] "Total todos" card: large count number (48px weight 600), label Geist Mono 11px uppercase `var(--muted)`, Postgres-blue accent indicator
    - [ ] "Done" card: count in `var(--green)`, colored dot/icon
    - [ ] "Overdue" card: count in `var(--red)`, colored dot/icon
  - [ ] **Distribution bar**: horizontal pill bar showing proportions of pending/done/overdue using `var(--bg-2)` / `var(--green)` / `var(--red)` segments, `border-radius: var(--radius-pill)`, height 8px
  - [ ] **Feature callout** info banner: left `var(--pg)` border, "MATERIALIZED VIEW is refreshed automatically after every INSERT, UPDATE, or DELETE on `todos_todo` via a Postgres trigger."
  - [ ] Scoping label when viewing own dashboard vs. another user's public list
- [ ] **Queue monitor page** (`todos/templates/todos/queue_monitor.html`)
  - [ ] Page header: kicker "Phase 7 · SELECT FOR UPDATE SKIP LOCKED", `<h1>Job Queue</h1>`
  - [ ] **Worker status bar**: pill strip showing worker count (e.g., "3 workers active"), bg `var(--bg-2)`, border `var(--rule-2)`, Geist Mono 12px — static display, no real-time
  - [ ] **Jobs table** wrapped in `.tbl-wrap` (border `var(--rule-2)`, radius 12px, `overflow: hidden`)
    - [ ] `<table>` with `<thead>` bg `var(--bg-2)`, `<th>` Geist Mono 10.5px uppercase `var(--muted)`
    - [ ] Columns: Job type, Todo title (truncated), Status badge (via `partials/badge.html`), Created at, Processed at
    - [ ] Hover row: subtle `rgba(20,24,29,.02)` bg
    - [ ] `select_related('todo')` already in view — ensure title renders via `job.todo.title`
  - [ ] **Empty queue state**: dashed border container, `⏸` icon, "Queue is empty", subtext "No jobs waiting. New todos enqueue a job via trigger."
  - [ ] **Feature callout** info banner: "Jobs are claimed with `SELECT … FOR UPDATE SKIP LOCKED` — multiple workers can run concurrently without double-processing."

---

### PR 23 — Design: Search + Users pages

> FTS results with ts_headline highlights and the user-discovery flow.

- [ ] **Search results page** (`todos/templates/todos/search_results.html`)
  - [ ] Page header: kicker "Phase 2 · tsvector + GIN index + ts_headline", `<h1>Search</h1>`
  - [ ] **Search bar**: 52px-height input with leading search SVG icon (16×16, stroke `var(--muted)`, 1.8 strokeWidth), bg `#fff`, border `var(--rule-2)`, radius `var(--radius-md)`, `box-shadow: var(--shadow-sm)` on focus; form `method="get"` with `name="q"`
  - [ ] **Result count meta** (when results present): "N results for 'query'" in Geist Mono 11.5px `var(--muted)`, shown above results list
  - [ ] **Result items** in `<ul>` — each `<li class="search-result">`:
    - [ ] Card-style: bg `var(--paper)`, border `var(--rule)`, radius 10px, padding `16px 20px`, shadow-sm, `margin-bottom: 8px`
    - [ ] Title: 16px, weight 600, `var(--ink)`, links to todo detail (or index with anchor)
    - [ ] Snippet: `.search-result__snippet` — `{{ todo.headline|safe }}` with CSS `b { background: #fef3c7; color: #7c4500; ... }` (per handoff §06)
    - [ ] Due date + status badge in a row at bottom of card
    - [ ] Rank annotation label (Geist Mono 10.5px `var(--muted)`): "rank 0.42" or equivalent
  - [ ] **Empty search state**: "tsvector" mono watermark, "No results for 'query'", "Try different keywords. Full-text search uses English stemming."
  - [ ] **No query state**: large search bar centered with "Search your todos" heading
- [ ] **User search page** (`accounts/templates/accounts/user_search.html`)
  - [ ] Page header: kicker "Accounts · username search", `<h1>Find users</h1>`
  - [ ] Same search bar pattern as search results (form `method="get"`, `name="q"`)
  - [ ] **User result cards** (when results): each card shows avatar initials circle (32px, bg `var(--bg-2)`, Geist Mono), username (weight 500), "View todos →" link button (secondary border style, links to `{% url 'accounts:user_todos' username=user.username %}`)
  - [ ] **Empty state**: "No users match 'query'" with subtext "Try a different username."
  - [ ] **No query state**: invitation text "Search for a user by username to view their public todo list."
- [ ] **Public user todo list** (`accounts/templates/accounts/user_todo_list.html`)
  - [ ] Page header: avatar initials + username + privacy badge ("Public" or "Private" pill)
  - [ ] If viewing own list: note "This is how others see your list" (info callout)
  - [ ] Todo rows: same `.todo-row` pattern as index, but without create form and without WebSocket script
  - [ ] **Inline FTS search**: `<form method="get">` search bar at top for filtering this user's visible todos (calls `?q=<term>`)
  - [ ] 403 page (if private list accessed by non-owner): centered error state with red banner and "Back to user search" link

---

### PR 24 — Design: Settings + system states + dark mode

> Privacy toggle, global error pages, and the optional dark mode mechanism.

- [ ] **Settings page** (`accounts/templates/accounts/user_settings.html`)
  - [ ] Page header: kicker "Accounts · privacy", `<h1>Settings</h1>`
  - [ ] **Privacy settings card**: bg `var(--paper)`, border `var(--rule-2)`, radius `var(--radius-xl)` (14px), padding 24px, shadow-card
    - [ ] Card title: "Todo list visibility" (weight 600, 16px)
    - [ ] Toggle row: label "Make my todo list public" with subtext "Anyone with the link can see your todos", and a `<form method="post">` checkbox toggle + "Save" button
    - [ ] Current status pill: "Private" (gray) or "Public" (green) badge using `.badge` component
    - [ ] Danger zone section below: description of what changing visibility means
  - [ ] **Success flash banner** on save: `messages.SUCCESS` → green `msg-banner--success` with "Settings saved" (rendered by `base.html` message block)
  - [ ] **Account info card**: read-only display of username, email, joined date — bg `var(--bg-2)`, radius `var(--radius-md)`, padding 16px, Geist Mono labels
- [ ] **System / empty states** (already covered in CSS, but verify in templates)
  - [ ] Confirm `.msg-banner--success/info/warning/error` renders correctly via the `base.html` messages block on all pages that use `messages.add_message`
  - [ ] 403 template: same nav shell, centered red `msg-banner--error` box, "Back" link
  - [ ] 404 template: same nav shell, "○" empty state icon, "Page not found", link to index
  - [ ] 500 template: same nav shell, red error state
- [ ] **Dark mode (optional — v0.2 target)**
  - [ ] Add `[data-theme="dark"]` token overrides to `base.css` (already specified in tokens task)
  - [ ] Add a theme-toggle button in the nav (small icon button, right of auth area) that sets/reads a `theme` cookie
  - [ ] Inline `<script>` in `base.html` `<head>` that reads the cookie and sets `document.documentElement.dataset.theme` before first paint (prevents flash)
  - [ ] Note: defer dark mode to post-MVP if it blocks other work

---

## What Postgres replaces

| Replaces        | Postgres feature                       | Phase |
| --------------- | -------------------------------------- | ----- |
| Elasticsearch   | `tsvector` + GIN index + `ts_headline` | 2     |
| Redis Pub/Sub   | `pg_notify` + `LISTEN`                 | 3     |
| Redis cache     | Materialized view + concurrent refresh | 4     |
| SQS / job queue | `SELECT FOR UPDATE SKIP LOCKED`        | 5     |
