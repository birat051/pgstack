from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('todos', '0003_add_gin_index'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION todos_todo_set_search_vector()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    NEW.search_vector := to_tsvector(
                        'english',
                        coalesce(NEW.title, '') || ' ' || coalesce(NEW.notes, '')
                    );
                    RETURN NEW;
                END;
                $$;

                CREATE TRIGGER todos_todo_search_vector_trg
                    BEFORE INSERT OR UPDATE ON todos_todo
                    FOR EACH ROW
                    EXECUTE FUNCTION todos_todo_set_search_vector();

                UPDATE todos_todo
                SET search_vector = to_tsvector(
                    'english',
                    coalesce(title, '') || ' ' || coalesce(notes, '')
                );
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS todos_todo_search_vector_trg ON todos_todo;
                DROP FUNCTION IF EXISTS todos_todo_set_search_vector();
            """,
        ),
    ]
