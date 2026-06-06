from django.db import migrations


class Migration(migrations.Migration):
    """Scope ``todo_stats`` by owner so dashboard counts stay per-user."""

    dependencies = [
        ('todos', '0010_add_todo_stats_refresh_trigger'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DROP TRIGGER IF EXISTS refresh_stats_trigger ON todos_todo;
                DROP INDEX IF EXISTS todo_stats_status_uidx;
                DROP MATERIALIZED VIEW IF EXISTS todo_stats;

                CREATE MATERIALIZED VIEW todo_stats AS
                SELECT
                    owner_id,
                    status,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE due_date < NOW()) AS overdue_count,
                    COUNT(*) FILTER (WHERE status = 'done') AS done_count
                FROM todos_todo
                GROUP BY owner_id, status;

                CREATE UNIQUE INDEX todo_stats_owner_status_uidx
                    ON todo_stats(owner_id, status);

                CREATE TRIGGER refresh_stats_trigger
                    AFTER INSERT OR UPDATE OR DELETE ON todos_todo
                    FOR EACH ROW
                    EXECUTE FUNCTION refresh_todo_stats();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS refresh_stats_trigger ON todos_todo;
                DROP INDEX IF EXISTS todo_stats_owner_status_uidx;
                DROP MATERIALIZED VIEW IF EXISTS todo_stats;

                CREATE MATERIALIZED VIEW todo_stats AS
                SELECT
                    status,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE due_date < NOW()) AS overdue_count,
                    COUNT(*) FILTER (WHERE status = 'done') AS done_count
                FROM todos_todo
                GROUP BY status;

                CREATE UNIQUE INDEX todo_stats_status_uidx ON todo_stats(status);

                CREATE TRIGGER refresh_stats_trigger
                    AFTER INSERT OR UPDATE OR DELETE ON todos_todo
                    FOR EACH ROW
                    EXECUTE FUNCTION refresh_todo_stats();
            """,
        ),
    ]
