from django.db import migrations


class Migration(migrations.Migration):
    """Refresh todo_stats after every todo write so dashboard counts stay current."""

    dependencies = [
        ('todos', '0009_add_todo_stats_view'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION refresh_todo_stats()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    REFRESH MATERIALIZED VIEW CONCURRENTLY todo_stats;
                    RETURN NULL;
                END;
                $$;

                CREATE TRIGGER refresh_stats_trigger
                    AFTER INSERT OR UPDATE OR DELETE ON todos_todo
                    FOR EACH ROW
                    EXECUTE FUNCTION refresh_todo_stats();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS refresh_stats_trigger ON todos_todo;
                DROP FUNCTION IF EXISTS refresh_todo_stats();
            """,
        ),
    ]
