from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Property
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from datetime import datetime, timezone

class Command(BaseCommand):
    help = "Экспорт объектов в формат Яндекс.Недвижимость"

    def handle(self, *args, **kwargs):
        root = Element("realty-feed")
        SubElement(root, "generation-date").text = datetime.now(timezone.utc).isoformat()
        offers = SubElement(root, "offers")
        for p in Property.objects.filter(is_published=True):
            offer = SubElement(offers, "offer", {"internal-id": p.external_id})
            SubElement(offer, "type").text = "продажа" if p.operation == "sale" else "аренда"
            SubElement(offer, "property-type").text = "жилая"
            SubElement(offer, "category").text = {"flat":"квартира","house":"дом","room":"комната","land":"участок"}[p.category]

            loc = SubElement(offer, "location")
            SubElement(loc, "country").text = p.country
            if p.region: SubElement(loc, "region").text = p.region
            SubElement(loc, "locality-name").text = p.city
            SubElement(loc, "address").text = p.address
            if p.latitude and p.longitude:
                SubElement(loc, "latitude").text = str(p.latitude)
                SubElement(loc, "longitude").text = str(p.longitude)

            price = SubElement(offer, "price")
            SubElement(price, "value").text = str(int(p.price))
            SubElement(price, "currency").text = p.currency

            SubElement(offer, "description").text = p.description or p.title

            for ph in p.photos.all():
                url = ""
                if getattr(ph, "image", None):
                    try:
                        url = f"{settings.SITE_BASE_URL}{ph.image.url}"
                    except ValueError:
                        url = ""
                if not url:
                    url = getattr(ph, "full_url", "")
                if not url:
                    continue
                SubElement(offer, "image").text = url

        out_dir = Path(settings.MEDIA_ROOT) / "feeds"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "yandex.xml"
        ElementTree(root).write(out_path, encoding="utf-8", xml_declaration=True)
        self.stdout.write(self.style.SUCCESS(f"OK: {out_path}"))
