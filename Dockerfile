# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System packages for psycopg2-binary wheels and general HTTPS/pip reliability.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos "" appuser

# Install deps first for better layer caching (see docs/PROJECT_GUIDELINES.MD — split by ENV).
COPY requirements/ requirements/
ARG ENV=prod
RUN pip install --no-cache-dir -r requirements/${ENV}.txt

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# wait_for_db: todos/management/commands/wait_for_db.py (PROJECT_GUIDELINES)
CMD ["sh", "-c", "python manage.py wait_for_db && python manage.py migrate && daphne -b 0.0.0.0 -p 8000 pgstack.asgi:application"]
