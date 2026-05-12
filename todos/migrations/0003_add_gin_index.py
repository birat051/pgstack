from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('todos', '0002_job'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE INDEX todos_search_gin
                ON todos_todo USING GIN(search_vector);
            """,
            reverse_sql="DROP INDEX IF EXISTS todos_search_gin;",
        ),
    ]
