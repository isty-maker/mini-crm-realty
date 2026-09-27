import os
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from core.models import Photo
from core.storage import YandexMediaStorage, is_yandex_storage_configured


class Command(BaseCommand):
    help = "Migrate local photos from PythonAnywhere filesystem to Yandex Object Storage idempotently."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate migration without uploading files to Yandex Object Storage.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        if not is_yandex_storage_configured() and not dry_run:
            self.stderr.write(
                self.style.ERROR(
                    "Yandex Object Storage is not configured in settings/.env! "
                    "Set YANDEX_STORAGE_BUCKET_NAME and YANDEX_CLIENT_KEY_ID."
                )
            )
            return

        storage = YandexMediaStorage()
        photos = Photo.objects.exclude(image="").exclude(image__isnull=True)
        total = photos.count()
        migrated = 0
        skipped = 0
        failed = 0

        self.stdout.write(f"Starting migration for {total} photo records...")

        for photo in photos:
            name = photo.image.name
            if not name:
                continue

            # Check if file exists on local MEDIA_ROOT
            local_path = Path(settings.MEDIA_ROOT) / name
            if not local_path.exists():
                self.stdout.write(
                    self.style.WARNING(f"[SKIP] Local file for Photo #{photo.id} ({name}) not found on disk.")
                )
                skipped += 1
                continue

            # Check if file already exists in Yandex Object Storage (idempotency check)
            if not dry_run:
                try:
                    if storage.exists(name):
                        self.stdout.write(
                            self.style.SUCCESS(f"[EXISTS] Photo #{photo.id} ({name}) already exists in Yandex Cloud.")
                        )
                        skipped += 1
                        continue
                except Exception as e:
                    self.stderr.write(
                        self.style.ERROR(f"[ERROR] Could not check status in Yandex Cloud for Photo #{photo.id}: {e}")
                    )
                    failed += 1
                    continue

            if dry_run:
                self.stdout.write(f"[DRY-RUN] Would upload Photo #{photo.id} ({name}) to Yandex Cloud.")
                migrated += 1
                continue

            try:
                content = local_path.read_bytes()
                storage.save(name, ContentFile(content))
                # Verify uploaded size if available
                uploaded_size = storage.size(name)
                local_size = local_path.stat().st_size
                if uploaded_size is not None and uploaded_size != local_size:
                    self.stderr.write(
                        self.style.ERROR(
                            f"[MISMATCH] Photo #{photo.id} size mismatch: local {local_size} vs cloud {uploaded_size}"
                        )
                    )
                    failed += 1
                else:
                    self.stdout.write(self.style.SUCCESS(f"[UPLOADED] Photo #{photo.id} ({name}) successfully."))
                    migrated += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"[FAILED] Failed uploading Photo #{photo.id} ({name}): {e}"))
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nMigration completed: {migrated} uploaded, {skipped} skipped, {failed} failed out of {total} total."
            )
        )
