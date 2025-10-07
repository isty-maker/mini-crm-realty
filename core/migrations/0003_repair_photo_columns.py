from django.db import migrations, connection


def ensure_photo_columns(apps, schema_editor):
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(core_photo)")
        cols = [row[1] for row in cursor.fetchall()]
        if "image" not in cols:
            cursor.execute("ALTER TABLE core_photo ADD COLUMN image varchar(100) NULL")
        if "url" not in cols:
            cursor.execute("ALTER TABLE core_photo ADD COLUMN url varchar(200) NULL")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_photo_image"),
    ]

    operations = [
        migrations.RunPython(ensure_photo_columns, migrations.RunPython.noop),
    ]
