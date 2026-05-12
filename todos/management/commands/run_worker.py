from django.core.management.base import BaseCommand

from todos.worker import process_jobs


class Command(BaseCommand):
    help = 'Run background job worker.'

    def handle(self, *args: object, **options: object) -> None:
        self.stdout.write(self.style.SUCCESS('Worker started.'))
        process_jobs()
