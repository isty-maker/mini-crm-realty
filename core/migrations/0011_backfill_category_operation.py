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

RU_OP = {"продажа": "sale", "аренда": "rent"}

KNOWN_LEGACY_NAMES = [
    "category_combined",
    "type_combined",
    "category_operation",
    "type",
    "kind",
]


def derive_cat_op(s: str):
    """Вернёт (cat, op) из строки формата 'flat(sale)' или 'квартира(аренда)'; иначе (None, None)."""
    if not s:
        return (None, None)
    s = str(s).strip().lower()

    m = re.search(r"\b(flat|room|house|commercial|land)\s*\(\s*(sale|rent)\s*\)", s, flags=re.I)
    if m:
        return (m.group(1).lower(), m.group(2).lower())

    p = re.search(r"([а-яёa-z]+)\s*\(\s*([а-яёa-z]+)\s*\)", s, flags=re.I)
    if p:
        cat_ru = next((v for k, v in RU_CAT.items() if k in p.group(1)), None)
        op_ru = next((v for k, v in RU_OP.items() if k in p.group(2)), None)
        if cat_ru and op_ru:
            return (cat_ru, op_ru)

    return (None, None)


def get_combined_value(obj):
    """Возвращает строку комбокатегории, если найдена."""
    # 1) Попытка по известным именам полей
    for name in KNOWN_LEGACY_NAMES:
        if hasattr(obj, name):
            val = getattr(obj, name)
            if isinstance(val, str) and "(" in val and ")" in val:
                return val

    # 2) Фолбэк: пробежаться по всем CharField и поискать скобки
    for f in obj._meta.fields:
        try:
            if f.get_internal_type() == "CharField":
                val = getattr(obj, f.name, "")
                if isinstance(val, str) and "(" in val and ")" in val:
                    return val
        except Exception:
            continue
    return None


def forwards(apps, schema_editor):
    Property = apps.get_model("core", "Property")

    for p in Property.objects.all():
        cat = getattr(p, "category", None)
        op = getattr(p, "operation", None)
        if cat and op:
            continue  # уже заполнено

        combined = get_combined_value(p)
        if not combined:
            continue

        dcat, dop = derive_cat_op(combined)
        updates = []
        if dcat and not cat:
            setattr(p, "category", dcat)
            updates.append("category")
        if dop and not op:
            setattr(p, "operation", dop)
            updates.append("operation")
        if updates:
            p.save(update_fields=updates)


def backwards(apps, schema_editor):
    # обратную миграцию не делаем
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_backfill_category_operation"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
