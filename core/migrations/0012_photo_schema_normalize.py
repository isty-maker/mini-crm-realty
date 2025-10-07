from django.db import connection, migrations, models
from django.utils import timezone


def safe_copy_url_to_full_url(apps, schema_editor):
    # если в таблице core_photo существует колонка `url` — скопируем в full_url
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info('core_photo')")
        cols = [r[1] for r in cursor.fetchall()]
    if "url" not in cols:
        return
    Photo = apps.get_model("core", "Photo")
    # читаем сырые пары (id, url)
    with connection.cursor() as cursor:
        try:
            cursor.execute(
                "SELECT id, url FROM core_photo WHERE url IS NOT NULL AND url != ''"
            )
            rows = cursor.fetchall()
        except Exception:
            rows = []
    for pid, old_url in rows:
        try:
            ph = Photo.objects.get(pk=pid)
            if not ph.full_url:
                ph.full_url = old_url
                ph.save(update_fields=["full_url"])
        except Photo.DoesNotExist:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_repair_photo_columns"),
    ]

    operations = [
        migrations.RenameField(
            model_name="photo",
            old_name="prop",
            new_name="property",
        ),
        migrations.AddField(
            model_name="photo",
            name="full_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="photo",
            name="sort",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="photo",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(
            safe_copy_url_to_full_url, reverse_code=migrations.RunPython.noop
        ),
        # УДАЛЯТЬ колонку `url` НЕ БУДЕМ (в разных средах её может не быть) — просто перестанем использовать.
        # Если очень нужно будет — отдельной миграцией и только после проверки схемы на проде.
    ]
