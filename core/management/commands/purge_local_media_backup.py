import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Photo
from core.storage import YandexMediaStorage, is_yandex_storage_configured


class Command(BaseCommand):
    help = "Purge local photo backup files from PythonAnywhere filesystem once confirmed uploaded to Yandex Cloud."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm purging local media backup files.",
        )

    def handle(self, *args, **options):
        if not options.get("confirm"):
            self.stderr.write(
                self.style.ERROR(
                    "Safety check: You must pass --confirm to purge local photo backups.\n"
                    "Example: python manage.py purge_local_media_backup --confirm"
                )
            )
            return

        if not is_yandex_storage_configured():
            self.stderr.write(
                self.style.ERROR(
                    "Safety check: Yandex Object Storage credentials are not set. "
                    "Cannot verify cloud backups before deleting local files."
                )
            )
            return

        storage = YandexMediaStorage()
        photos = Photo.objects.exclude(image="").exclude(image__isnull=True)
        deleted = 0
        skipped = 0

        for photo in photos:
            name = photo.image.name
            if not name:
                continue

            local_path = Path(settings.MEDIA_ROOT) / name
            if not local_path.exists():
                continue

            # Double-check that cloud copy exists before unlinking local file
            try:
                if storage.exists(name):
                    os.remove(local_path)
                    deleted += 1
                else:
                    self.stderr.write(
                        self.style.WARNING(
                            f"[PRESERVED] Photo #{photo.id} ({name}) not found in Yandex Cloud; skipping local delete."
                        )
                    )
                    skipped += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error checking cloud storage for Photo #{photo.id}: {e}"))
                skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Purge complete: {deleted} local files removed, {skipped} preserved."))
