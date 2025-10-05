from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_backfill_category_operation"),
    ]

    operations = [
        migrations.RenameField(
            model_name="property",
            old_name="export_to_domclick",
            new_name="export_to_domklik",
        ),
        migrations.AlterField(
            model_name="property",
            name="export_to_domklik",
            field=models.BooleanField(default=False),
        ),
    ]
