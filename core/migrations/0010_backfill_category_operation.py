from django.db import migrations
import re


RU_CAT = {
    "квартира": "flat",
    "комната": "room",
    "дом": "house",
    "коттедж": "house",
    "дача": "house",
    "таунхаус": "house",
    "коммерц": "commercial",
    "коммерческ": "commercial",
    "земл": "land",
    "участок": "land",
}

RU_OP = {
    "продажа": "sale",
    "аренда": "rent",
}


def derive_cat_op(s):
    s = (s or "").strip().lower()
    if not s:
        return (None, None)
    m = re.search(r"(flat|room|house|commercial|land)\s*\(\s*(sale|rent)\s*\)", s)
    if m:
        return (m.group(1), m.group(2))
    p = re.search(r"([а-яёa-z]+)\s*\(\s*([а-яёa-z]+)\s*\)", s, re.I)
    if p:
        cat = next((v for k, v in RU_CAT.items() if k in p.group(1)), None)
        op = next((v for k, v in RU_OP.items() if k in p.group(2)), None)
        return (cat, op)
    return (None, None)


def forwards(apps, schema_editor):
    Property = apps.get_model("core", "Property")
    legacy_name = None
    for f in Property._meta.fields:
        choices = getattr(f, "choices", None) or []
        for ch in choices:
            if isinstance(ch, (list, tuple)) and len(ch) == 2:
                val, lab = ch
                if isinstance(lab, (list, tuple)):
                    if any(("(" in str(l) and ")" in str(l)) for _, l in lab):
                        legacy_name = f.name
                        break
                else:
                    if "(" in str(val) and ")" in str(val):
                        legacy_name = f.name
                        break
                    if "(" in str(lab) and ")" in str(lab):
                        legacy_name = f.name
                        break
        if legacy_name:
            break

    if not legacy_name:
        return

    for p in Property.objects.all():
        if getattr(p, "category", None) and getattr(p, "operation", None):
            continue
        combined = getattr(p, legacy_name, None)
        if not combined:
            continue
        cat, op = derive_cat_op(combined)
        update_fields = []
        if cat and not getattr(p, "category", None):
            setattr(p, "category", cat)
            update_fields.append("category")
        if op and not getattr(p, "operation", None):
            setattr(p, "operation", op)
            update_fields.append("operation")
        if update_fields:
            p.save(update_fields=update_fields)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_alter_property_external_id_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
