from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Property
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from django.utils.timezone import now

def add(parent, tag, value):
    el = SubElement(parent, tag)
    if value is None: value = ""
    el.text = str(value)
    return el

class Command(BaseCommand):
    help = "Экспорт объектов в формат ЦИАН 2.0"

    def handle(self, *args, **kwargs):
        root = Element("feed")
        SubElement(root, "feed_version").text = "2"
        for p in Property.objects.filter(is_published=True):
            o = SubElement(root, "object")
            add(o, "external_id", p.external_id)
            add(o, "category", {"flat":"квартира","house":"дом","room":"комната","land":"участок"}[p.category])
            add(o, "deal_type", {"sale":"продажа","rent":"аренда"}[p.operation])

            addr = SubElement(o, "address")
            add(addr, "country", p.country)
            add(addr, "region", p.region)
            add(addr, "city", p.city)
            add(addr, "street", p.address)

            if p.latitude and p.longitude:
                geo = SubElement(o, "coordinates")
                add(geo, "lat", p.latitude)
                add(geo, "lng", p.longitude)

            params = SubElement(o, "params")
            if p.rooms: add(params, "rooms_count", p.rooms)
            if p.floor is not None: add(params, "floor_number", p.floor)
            if p.floors_total: add(params, "floors_count", p.floors_total)
            if p.area_total: add(params, "total_area", p.area_total)

            price = SubElement(o, "price")
            add(price, "value", int(p.price))
            add(price, "currency", p.currency)

            add(o, "description", p.description or p.title)

            contacts = SubElement(o, "contacts")
            if p.agent:
                add(contacts, "name", p.agent.name)
                add(contacts, "phone", p.agent.phone or "")
                add(contacts, "email", p.agent.email or "")

            pics = SubElement(o, "photos")
            for ph in p.photos.all():
                src = ph.src
                if not src:
                    continue
                if src.startswith("http://") or src.startswith("https://"):
                    url = src
                else:
                    url = f"{settings.SITE_BASE_URL}{src}"
                add(pics, "photo", url)

        out_dir = Path(settings.MEDIA_ROOT) / "feeds"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "cian.xml"
        ElementTree(root).write(out_path, encoding="utf-8", xml_declaration=True)
        self.stdout.write(self.style.SUCCESS(f"OK: {out_path} ({now()})"))
