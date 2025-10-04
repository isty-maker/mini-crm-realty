import uuid

from django.core.management.base import BaseCommand

from core.models import Property


def gen_eid():
    return f"OBJ-{uuid.uuid4().hex[:8]}"


class Command(BaseCommand):
    help = "Проставляет уникальные external_id там, где они пустые или NULL"

    def handle(self, *args, **kwargs):
        field = Property._meta.get_field("external_id")
        if getattr(field, "null", False):
            qs = Property.objects.filter(external_id__isnull=True)
        else:
            qs = Property.objects.none()
        try:
            empty = Property.objects.filter(external_id="")
            qs = qs | empty
        except Exception:
            pass  # если поле не поддерживает пустую строку

        updated = 0
        for p in qs:
            eid = gen_eid()
            # гарантируем уникальность
            while Property.objects.filter(external_id=eid).exists():
                eid = gen_eid()
            p.external_id = eid
            p.save(update_fields=["external_id"])
            updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated: {updated}"))
