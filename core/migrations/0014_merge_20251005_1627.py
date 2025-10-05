from django.core.exceptions import FieldDoesNotExist
from django.db import migrations


class SafeRenameField(migrations.RenameField):
    def state_forwards(self, app_label, state):
        try:
            super().state_forwards(app_label, state)
        except FieldDoesNotExist:
            # State already uses the new field name; nothing else to do.
            pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_rename_export_to_domklik"),
        ("core", "0013_property_is_archived_property_operation_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Database rename handled earlier; this merge keeps state aligned.
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
