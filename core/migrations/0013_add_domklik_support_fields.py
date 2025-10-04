from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_rename_export_to_domklik"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="operation",
            field=models.CharField(
                blank=True,
                choices=[
                    ("sale", "Продажа"),
                    ("rent_long", "Аренда"),
                    ("rent_daily", "Посуточно"),
                ],
                max_length=20,
                null=True,
                verbose_name="Тип сделки",
            ),
        ),
        migrations.AddField(
            model_name="property",
            name="subtype",
            field=models.CharField(blank=True, max_length=30, null=True, verbose_name="Подтип"),
        ),
        migrations.AddField(
            model_name="property",
            name="is_archived",
            field=models.BooleanField(default=False, verbose_name="В архиве"),
        ),
    ]
