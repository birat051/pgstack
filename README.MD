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

## What Postgres is doing

| Feature                          | Replaces      | How                                                |
| -------------------------------- | ------------- | -------------------------------------------------- |
| Full-text search                 | Elasticsearch | `tsvector` + `tsquery` + GIN index + `ts_headline` |
| Live updates across browser tabs | Redis Pub/Sub | `pg_notify` + `LISTEN` + Django Channels           |
| Aggregation dashboard            | Redis cache   | `MATERIALIZED VIEW` + `REFRESH CONCURRENTLY`       |
| Background job queue             | SQS + Celery  | `SELECT FOR UPDATE SKIP LOCKED`                    |

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

## Running pgstack

The only prerequisites are Docker and Docker Compose.

```bash
git clone https://github.com/yourname/pgstack.git
cd pgstack

cp .env.example .env

docker compose up --build
```

Visit [http://localhost:8000](http://localhost:8000).

---

## The demo

Once the app is running, here is what to try:

**1. Live updates** — open [http://localhost:8000](http://localhost:8000) in two browser tabs side by side. Create a TODO in one tab. Watch it appear in the other without a page reload. That is a Postgres `NOTIFY` trigger firing through a Django Channels WebSocket consumer. No Redis.

**2. Full-text search** — go to [/search/](http://localhost:8000/search/) and search for any word in a TODO title or note. Results come back ranked by relevance with matching terms highlighted. That is `tsvector`, `ts_rank`, and `ts_headline`. No Elasticsearch.

**3. Dashboard** — go to [/dashboard/](http://localhost:8000/dashboard/) and see live counts by status. The numbers are read from a Postgres materialized view that refreshes itself after every write via a trigger. No Redis cache, no cache warming, no TTL to worry about.

**4. Job queue** — go to [/queue/](http://localhost:8000/queue/) and watch background jobs move from `queued → processing → done` in real time. The `worker` service uses `SELECT FOR UPDATE SKIP LOCKED` to pull jobs atomically. Scale it up with `docker compose up --scale worker=3` and confirm no job is ever processed twice. No SQS, no Celery.

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
└── todos/                # the one app
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

## Further reading

If pgstack made you curious about what Postgres can really do, these are worth reading:

- [PostgreSQL Full Text Search](https://www.postgresql.org/docs/current/textsearch.html) — official docs
- [LISTEN / NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html) — official docs
- [Materialized Views](https://www.postgresql.org/docs/current/rules-materializedviews.html) — official docs
- [SELECT FOR UPDATE SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE) — official docs
- [Is Postgres good enough?](https://www.amazingcto.com/postgres-for-everything/) — the blog post that inspired this project

---

## Tech stack

- [Django](https://www.djangoproject.com/) — web framework (MVT)
- [Django Channels](https://channels.readthedocs.io/) — ASGI + WebSockets
- [PostgreSQL 16](https://www.postgresql.org/) — doing everything
- [Daphne](https://github.com/django/daphne) — ASGI server
- [Docker + Compose](https://docs.docker.com/compose/) — local environment

---

_Built to learn. Not for production. Have fun._
