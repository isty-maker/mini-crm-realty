from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_property_is_archived_property_operation_and_more"),
    ]

    operations = [
        # no-op: эта миграция теперь ничего не меняет ни в state, ни в БД.
    ]
