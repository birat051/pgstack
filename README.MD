# pgstack

A TODO app with no Redis, no Elasticsearch, and no SQS.

Just Django, a few templates, and one Postgres instance doing things most developers don't know it can.

---

## What is this?

pgstack is a learning project built to answer one question:

> _How far can you push Postgres before you actually need another service?_

The answer, it turns out, is pretty far. Full-text search, live pub/sub, a read-through cache, and a concurrent job queue — all running inside the same database your todos are stored in.

It is built with Django's MVT architecture — server-rendered templates, no JavaScript framework, no REST API. The goal is to keep the application layer as thin as possible so the Postgres features do the talking.

---

## What Postgres replaces

| Replaces        | Postgres feature                                   |
| --------------- | -------------------------------------------------- |
| Elasticsearch   | `tsvector` + `tsquery` + GIN index + `ts_headline` |
| Redis Pub/Sub   | `pg_notify` + `LISTEN` + Django Channels           |
| Redis cache     | `MATERIALIZED VIEW` + `REFRESH CONCURRENTLY`       |
| SQS / Celery    | `SELECT FOR UPDATE SKIP LOCKED`                    |

---

## Auth and privacy

Todos are **user-owned**: every todo has an `owner` foreign key, and authenticated users only see their own list on `/`, `/search/`, `/dashboard/`, and `/queue/`.

Todo lists are **private by default**. New accounts get `UserSettings.is_todo_list_private = True`. Other users cannot browse a private list at `/users/<username>/todos/` (404). To share, go to **Settings** and turn off "Keep my todo list private"; then others can find you under **Users** and view your public todos.

Live WebSocket updates on `/` are scoped to the logged-in user's own todos — NOTIFY payloads are filtered by `owner_id` before reaching the browser.

---

## Prerequisites

Docker and Docker Compose only. No local Python env or Postgres install required.

---

## Setup

```bash
git clone https://github.com/yourname/pgstack.git
cd pgstack

cp .env.example .env

docker compose up --build
```

Visit [http://localhost:8000](http://localhost:8000).

The stack runs three services:

| Service  | Role                                      |
| -------- | ----------------------------------------- |
| `db`     | PostgreSQL 16                             |
| `web`    | Daphne ASGI — Django + Channels on `:8000` |
| `worker` | Background job processor (`run_worker`)   |

---

## Demo script

Run through these steps after `docker compose up --build`. Use two browser profiles (or one normal + one incognito window) for the two-user flow.

### 0. Register and sign in

1. Open [http://localhost:8000/auth/signup/](http://localhost:8000/auth/signup/) and create **User A** (name, email, password).
2. Create a few todos from the home page (`/`).
3. Sign out, then register **User B** in a second profile.
4. As User B, visit `/users/<user_a_username>/todos/` — you should get **404** (User A's list is private by default).
5. As User A, go to [Settings](http://localhost:8000/settings/) and uncheck "Keep my todo list private", then save.
6. As User B, go to [Users](http://localhost:8000/users/search/?q=<user_a_username>) and open User A's public todo list — you should see User A's todos, not your own.

### 1. Live updates (LISTEN / NOTIFY)

Open [http://localhost:8000](http://localhost:8000) in **two tabs** while signed in as the same user. Create a todo in tab A; it appears in tab B without a reload. That is a Postgres `NOTIFY` trigger → Django Channels WebSocket consumer. No Redis.

### 2. Full-text search (FTS)

Go to [http://localhost:8000/search/](http://localhost:8000/search/) and search for a word in a todo title or note. Results are ranked with matching terms highlighted via `ts_headline`. No Elasticsearch.

### 3. Dashboard (materialized view)

Go to [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/). Counts by status come from the `todo_stats` materialized view, refreshed automatically after every write via a Postgres trigger. Counts are scoped to your todos only.

### 4. Job queue (SKIP LOCKED)

Go to [http://localhost:8000/queue/](http://localhost:8000/queue/). Each new todo enqueues a job; the `worker` service claims rows with `SELECT … FOR UPDATE SKIP LOCKED`. Refresh the page to watch jobs move `queued → processing → done`. Scale workers with:

```bash
docker compose up --scale worker=3
```

Create several todos and confirm no job is processed twice. Queue rows are scoped to your todos — User B never sees User A's private jobs.

---

## Running tests

Inside Docker (uses the same Postgres instance as the app):

```bash
docker compose run --rm web python manage.py test
```

Key suites covering the demo flows: `accounts.tests`, `todos.tests.test_navigation`, `todos.tests.test_downstream`, `todos.tests.test_consumers`.

---

## Project structure

```
pgstack/
├── docker-compose.yml
├── Dockerfile
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── pgstack/              # Django project config
│   ├── settings/
│   ├── asgi.py
│   └── urls.py
├── accounts/             # signup, settings, user search, public lists
│   ├── models.py         # UserSettings (privacy)
│   ├── services.py
│   ├── views.py
│   └── templates/
└── todos/                # todos, search, dashboard, queue, WebSocket
    ├── models.py
    ├── services.py
    ├── views.py
    ├── consumers.py
    ├── worker.py
    ├── migrations/
    ├── templates/todos/
    └── tests/
```

---

## ⚠️ Caveats — please read this

**pgstack is a fun project. It is not a production architecture recommendation.**

Every feature demonstrated here has real limitations at scale that the dedicated tools are designed to solve. Before reaching for any of these patterns in a production system, you should understand the trade-offs:

**Full-text search** — Postgres FTS is genuinely good for moderate data volumes and simple ranking needs. It will not match Elasticsearch on faceted search, custom tokenisers, distributed indexing across hundreds of millions of documents, or the query DSL flexibility that search-heavy products need.

**LISTEN / NOTIFY** — Postgres pub/sub works well for low-to-moderate event rates on a single database node. It does not fan out across replicas, has no message persistence (if your consumer is offline when a notification fires, it is gone), and does not scale horizontally the way Redis Pub/Sub or Kafka do. For anything requiring guaranteed delivery or high fan-out, use a real message broker.

**Materialized views as a cache** — `REFRESH MATERIALIZED VIEW CONCURRENTLY` is non-blocking, but it is still a full recompute on every refresh. For dashboards with complex aggregations over large tables, this adds write overhead. Redis gives you O(1) cache writes with explicit TTL control. The materialized view approach here is appropriate for low-write workloads where you want simplicity over performance.

**SKIP LOCKED as a job queue** — this pattern is solid and used in production by tools like [Oban](https://github.com/sorentwo/oban) (Elixir) and [Que](https://github.com/que-rb/que) (Ruby). The caveat is that it adds load to your primary database, and at high job volumes you will eventually want a dedicated queue service that does not compete with your transactional workload for connections and I/O. For pgstack's scope, it is a great fit.

**In short** — if you are running a side project, an internal tool, or an early-stage product, these patterns can meaningfully reduce your infrastructure complexity. If you are running at scale, use the right tool for the job.

---

## Further reading

If pgstack made you curious about what Postgres can really do, these are worth reading:

- [PostgreSQL Full Text Search](https://www.postgresql.org/docs/current/textsearch.html) — official docs
- [LISTEN / NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html) — official docs
- [Materialized Views](https://www.postgresql.org/docs/current/rules-materializedviews.html) — official docs
- [SELECT FOR UPDATE SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE) — official docs
- [Is Postgres good enough?](https://www.amazingcto.com/postgres-for-everything/) — the blog post that inspired this project

Project docs in this repo: [`docs/ARCHITECTURE.MD`](docs/ARCHITECTURE.MD), [`docs/PROJECT_GUIDELINES.MD`](docs/PROJECT_GUIDELINES.MD).

---

## Tech stack

- [Django](https://www.djangoproject.com/) — web framework (MVT)
- [Django Channels](https://channels.readthedocs.io/) — ASGI + WebSockets
- [PostgreSQL 16](https://www.postgresql.org/) — doing everything
- [Daphne](https://github.com/django/daphne) — ASGI server
- [Docker + Compose](https://docs.docker.com/compose/) — local environment

---

_Built to learn. Not for production. Have fun._
