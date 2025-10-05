from django.core.exceptions import FieldDoesNotExist
from django.db import migrations


class SafeRenameField(migrations.RenameField):
    def state_forwards(self, app_label, state):
        try:
            super().state_forwards(app_label, state)
        except FieldDoesNotExist:
            # State already uses the new field name; no further action needed.
            pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_property_is_archived_property_operation_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Никаких DB-операций здесь. БД мы уже приводили ранее (0012).
            ],
            state_operations=[
                SafeRenameField(
                    model_name="property",
                    old_name="export_to_domclick",
                    new_name="export_to_domklik",
                ),
            ],
        ),
    ]
