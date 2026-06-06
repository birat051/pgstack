from django.db import migrations


class Migration(migrations.Migration):
    """Enqueue a ``send_reminder`` job when a todo row is inserted."""

    dependencies = [
        ('todos', '0011_todo_stats_scope_by_owner'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION enqueue_todo_job()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    INSERT INTO todos_job (todo_id, job_type, payload, status, created_at)
                    VALUES (
                        NEW.id,
                        'send_reminder',
                        row_to_json(NEW),
                        'queued',
                        NOW()
                    );
                    PERFORM pg_notify('job_queue', NEW.id::text);
                    RETURN NEW;
                END;
                $$;

                CREATE TRIGGER todo_enqueue_trigger
                    AFTER INSERT ON todos_todo
                    FOR EACH ROW
                    EXECUTE FUNCTION enqueue_todo_job();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS todo_enqueue_trigger ON todos_todo;
                DROP FUNCTION IF EXISTS enqueue_todo_job();
            """,
        ),
    ]
