from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.cian import build_cian_feed_xml
from core.models import Property


class Command(BaseCommand):
    help = "Generate CIAN feed XML (Feed_Version=2) into media/feeds/cian.xml"

    def add_arguments(self, parser):
        parser.add_argument(
            "--stdout",
            action="store_true",
            help="Print the generated XML to stdout instead of saving only to a file.",
        )

    def handle(self, *args, **options):
        queryset = (
            Property.objects.filter(export_to_cian=True, is_archived=False)
            .order_by("id")
            .prefetch_related("photos")
        )

        xml_bytes = build_cian_feed_xml(queryset)

        feeds_dir = Path(settings.MEDIA_ROOT) / "feeds"
        feeds_dir.mkdir(parents=True, exist_ok=True)
        out_path = feeds_dir / "cian.xml"
        out_path.write_bytes(xml_bytes)

        if options.get("stdout"):
            self.stdout.write(xml_bytes.decode("utf-8"))

        self.stdout.write(self.style.SUCCESS(f"CIAN feed saved to {out_path}"))
