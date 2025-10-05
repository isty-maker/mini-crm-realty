from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_rename_export_to_domklik"),
        ("core", "0015_merge_linearize"),
    ]

    operations = [
        # no-op: this migration only merges heads to linearize the graph
    ]
