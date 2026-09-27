import os
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from core.cian import build_cian_feed_xml
from core.models import Property
from core.storage import YandexFeedStorage, is_yandex_storage_configured


def generate_and_save_feed(filename: str, export_field: str) -> str:
    filter_kwargs = {export_field: True, "is_archived": False}
    queryset = (
        Property.objects.filter(**filter_kwargs)
        .order_by("id")
        .prefetch_related("photos")
    )
    xml_bytes = build_cian_feed_xml(queryset)

    # Save locally under MEDIA_ROOT/feeds/
    local_feeds_dir = Path(settings.MEDIA_ROOT) / "feeds"
    local_feeds_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_feeds_dir / filename
    local_path.write_bytes(xml_bytes)

    # If Yandex Object Storage is configured, save to feeds/ in storage as well
    if is_yandex_storage_configured():
        storage = YandexFeedStorage()
        storage_name = f"feeds/{filename}"
        storage.save(storage_name, ContentFile(xml_bytes))
        return storage.url(storage_name)

    return f"/media/feeds/{filename}"


class Command(BaseCommand):
    help = "Generate CIAN feed XML (Feed_Version=2) into media/feeds/cian.xml and Yandex Object Storage"

    def add_arguments(self, parser):
        parser.add_argument(
            "--stdout",
            action="store_true",
            help="Print the generated XML to stdout instead of saving only to a file.",
        )

    def handle(self, *args, **options):
        cian_url = generate_and_save_feed("cian.xml", "export_to_cian")
        domklik_url = generate_and_save_feed("domklik.xml", "export_to_domklik")

        if options.get("stdout"):
            filter_kwargs = {"export_to_cian": True, "is_archived": False}
            queryset = (
                Property.objects.filter(**filter_kwargs)
                .order_by("id")
                .prefetch_related("photos")
            )
            xml_bytes = build_cian_feed_xml(queryset)
            self.stdout.write(xml_bytes.decode("utf-8"))

        self.stdout.write(self.style.SUCCESS(f"CIAN feed saved: {cian_url}"))
        self.stdout.write(self.style.SUCCESS(f"Domklik feed saved: {domklik_url}"))
