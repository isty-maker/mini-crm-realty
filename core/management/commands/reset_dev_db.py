from django.conf import settings
from django.core.management import BaseCommand, call_command

import os


class Command(BaseCommand):
    help = "DEV ONLY: drop local SQLite DB and re-create schema from 0001_initial"

    def handle(self, *args, **opts):
        db_path = getattr(settings, "DATABASES", {}).get("default", {}).get("NAME")
        if not db_path or not os.path.isfile(db_path):
            self.stdout.write(
                self.style.WARNING(f"DB file not found: {db_path}. Continuing...")
            )
        else:
            os.remove(db_path)
            self.stdout.write(self.style.SUCCESS(f"Removed SQLite DB: {db_path}"))

        call_command("migrate", interactive=False)
        self.stdout.write(self.style.SUCCESS("Fresh DB migrated."))
