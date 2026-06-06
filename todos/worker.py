"""SKIP LOCKED job processor — pulls queued rows and dispatches by ``job_type``."""

from __future__ import annotations

import logging
import time

from django.db import transaction
from django.utils import timezone

from todos.models import Job, JobStatus

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 0.5


def acquire_job() -> Job | None:
    """Return the next queued job row locked with SKIP LOCKED, or ``None``."""
    with transaction.atomic():
        return (
            Job.objects.select_for_update(skip_locked=True)
            .filter(status=JobStatus.QUEUED)
            .order_by('created_at')
            .first()
        )


def claim_next_job() -> Job | None:
    """Atomically claim the next queued job and mark it ``processing``."""
    with transaction.atomic():
        job = (
            Job.objects.select_for_update(skip_locked=True)
            .filter(status=JobStatus.QUEUED)
            .order_by('created_at')
            .first()
        )
        if job is None:
            return None
        mark_processing(job)
        return job


def mark_processing(job: Job) -> None:
    Job.objects.filter(id=job.id).update(status=JobStatus.PROCESSING)


def mark_complete(job: Job) -> None:
    Job.objects.filter(id=job.id).update(
        status=JobStatus.DONE,
        processed_at=timezone.now(),
    )


def mark_failed(job: Job) -> None:
    Job.objects.filter(id=job.id).update(
        status=JobStatus.FAILED,
        processed_at=timezone.now(),
    )


def handle_job(job: Job) -> None:
    if job.job_type == 'send_reminder':
        handle_send_reminder(job)
        return
    raise ValueError(f'Unknown job_type: {job.job_type!r}')


def handle_send_reminder(job: Job) -> None:
    """Demo handler — validates payload; no outbound email in this stack."""
    title = job.payload.get('title') if job.payload else None
    if not title:
        raise ValueError('send_reminder job missing title in payload')
    logger.info('send_reminder for todo %s: %s', job.todo_id, title)


def process_one_job() -> bool:
    """Claim and run one queued job. Returns ``False`` when the queue is empty."""
    job = claim_next_job()
    if job is None:
        return False
    try:
        handle_job(job)
        mark_complete(job)
    except Exception:
        logger.exception('Job %s failed', job.id)
        mark_failed(job)
    return True


def process_jobs() -> None:
    """Poll the queue forever, sleeping between attempts."""
    while True:
        process_one_job()
        time.sleep(POLL_INTERVAL_SECONDS)
