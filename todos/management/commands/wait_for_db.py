import time

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = 'Block until the default database accepts connections.'

    def handle(self, *args: object, **options: object) -> None:
        while True:
            try:
                with connections['default'].cursor():
                    pass
            except OperationalError:
                self.stdout.write('Waiting for database...')
                time.sleep(1)
            else:
                break
        self.stdout.write(self.style.SUCCESS('Database ready.'))
