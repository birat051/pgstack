from django.db import migrations


class Migration(migrations.Migration):
    """
    Notify `todo_updates` after todo changes. Payload is bounded (see PROJECT_GUIDELINES.MD:
    pg_notify max ~8000 bytes); not full row_to_json(NEW).
    """

    dependencies = [
        ('todos', '0005_add_search_document_trgm'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION todos_todo_notify_update()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                DECLARE
                    payload text;
                BEGIN
                    payload := json_build_object(
                        'id', NEW.id,
                        'title', NEW.title,
                        'status', NEW.status,
                        'due_date', NEW.due_date,
                        'created_at', NEW.created_at,
                        'notes_preview', left(coalesce(NEW.notes, ''), 512)
                    )::text;
                    IF octet_length(payload) > 7500 THEN
                        payload := json_build_object(
                            'id', NEW.id,
                            'title', NEW.title,
                            'status', NEW.status
                        )::text;
                    END IF;
                    PERFORM pg_notify('todo_updates', payload);
                    RETURN NEW;
                END;
                $$;

                CREATE TRIGGER todos_todo_notify_trg
                    AFTER INSERT OR UPDATE ON todos_todo
                    FOR EACH ROW
                    EXECUTE FUNCTION todos_todo_notify_update();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS todos_todo_notify_trg ON todos_todo;
                DROP FUNCTION IF EXISTS todos_todo_notify_update();
            """,
        ),
    ]
