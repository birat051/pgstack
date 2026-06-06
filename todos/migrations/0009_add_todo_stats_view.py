from django.db import migrations


class Migration(migrations.Migration):
    """Pre-computed per-status todo counts for the dashboard (Phase 6)."""

    dependencies = [
        ('todos', '0008_todo_notify_payload_owner'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE MATERIALIZED VIEW todo_stats AS
                SELECT
                    status,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE due_date < NOW()) AS overdue_count,
                    COUNT(*) FILTER (WHERE status = 'done') AS done_count
                FROM todos_todo
                GROUP BY status;

                CREATE UNIQUE INDEX todo_stats_status_uidx ON todo_stats(status);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS todo_stats_status_uidx;
                DROP MATERIALIZED VIEW IF EXISTS todo_stats;
            """,
        ),
    ]
