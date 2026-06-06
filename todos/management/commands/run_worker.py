from django.core.management.base import BaseCommand

from todos.worker import process_jobs


class Command(BaseCommand):
    help = 'Poll the job queue with SKIP LOCKED and process queued rows.'

    def handle(self, *args: object, **options: object) -> None:
        self.stdout.write(self.style.SUCCESS('Worker started.'))
        try:
            process_jobs()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Worker stopped.'))
