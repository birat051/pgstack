import time

from django.db import connection


def process_jobs() -> None:
    """SKIP LOCKED worker logic arrives in PR 11+."""
    while True:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        time.sleep(60)
