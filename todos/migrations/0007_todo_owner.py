import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def delete_unowned_todos(apps, schema_editor) -> None:
    """Remove rows that never had an owner; not reversible (deleted data cannot be restored)."""
    Todo = apps.get_model('todos', 'Todo')
    Todo.objects.filter(owner_id__isnull=True).delete()


class Migration(migrations.Migration):
    """Todo.owner + composite index for per-user list ordering.

    Postgres on `todos_todo` has BEFORE/AFTER ROW triggers from prior migrations.
    Deferred trigger events block `ALTER TABLE` in the same transaction as DML
    that touches those rows, so operations must commit between steps (atomic=False).
    """

    atomic = False

    dependencies = [
        ('todos', '0006_todo_notify_trigger'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='todo',
            name='owner',
            field=models.ForeignKey(
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='todos',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(delete_unowned_todos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='todo',
            name='owner',
            field=models.ForeignKey(
                db_index=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='todos',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name='todo',
            index=models.Index(
                fields=['owner', '-created_at'],
                name='todo_owner_created_at_desc_idx',
            ),
        ),
    ]
