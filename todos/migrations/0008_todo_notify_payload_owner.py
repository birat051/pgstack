from django.db import migrations


class Migration(migrations.Migration):
    """Include `owner_id` in todo_updates NOTIFY payload so WebSocket consumers filter without replaying NOTIFY to every client."""

    dependencies = [
        ('todos', '0007_todo_owner'),
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
                        'owner_id', NEW.owner_id,
                        'title', NEW.title,
                        'status', NEW.status,
                        'due_date', NEW.due_date,
                        'created_at', NEW.created_at,
                        'notes_preview', left(coalesce(NEW.notes, ''), 512)
                    )::text;
                    IF octet_length(payload) > 7500 THEN
                        payload := json_build_object(
                            'id', NEW.id,
                            'owner_id', NEW.owner_id,
                            'title', NEW.title,
                            'status', NEW.status
                        )::text;
                    END IF;
                    PERFORM pg_notify('todo_updates', payload);
                    RETURN NEW;
                END;
                $$;
            """,
            reverse_sql="""
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
            """,
        ),
    ]
