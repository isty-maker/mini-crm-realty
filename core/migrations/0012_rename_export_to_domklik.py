from django.db import connection, migrations


def _ensure_domklik_column(apps, schema_editor):
    """
    Make DB tolerant:
    - If 'export_to_domclick' exists and 'export_to_domklik' doesn't, rename the column.
    - Else if neither exists, add 'export_to_domklik' as boolean default 0.
    """
    Property = apps.get_model("core", "Property")
    table = Property._meta.db_table

    with connection.cursor() as cursor:
        # Collect column names
        try:
            cols = [c.name for c in connection.introspection.get_table_description(cursor, table)]
        except Exception:
            cols = []

        has_old = "export_to_domclick" in cols
        has_new = "export_to_domklik" in cols

        if has_old and not has_new:
            # Try SQL rename (works on modern SQLite/Postgres)
            try:
                cursor.execute(
                    f'ALTER TABLE "{table}" RENAME COLUMN "export_to_domclick" TO "export_to_domklik";'
                )
            except Exception:
                # Fallback: add new, copy values, drop old (SQLite variant if needed)
                cursor.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "export_to_domklik" BOOLEAN NOT NULL DEFAULT 0;'
                )
                # copy truthy values from old to new if DB supports boolean/int cast
                try:
                    cursor.execute(
                        f'UPDATE "{table}" SET "export_to_domklik" = COALESCE("export_to_domclick", 0);'
                    )
                except Exception:
                    pass
                # old column drop is optional (SQLite may need table rebuild); we can leave it
        elif not has_old and not has_new:
            # Fresh DB without the column at all — add it
            try:
                cursor.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "export_to_domklik" BOOLEAN NOT NULL DEFAULT 0;'
                )
            except Exception:
                pass
        # If has_new already — nothing to do.


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_backfill_category_operation"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    _ensure_domklik_column, reverse_code=migrations.RunPython.noop
                ),
            ],
            state_operations=[
                # Keep state as-is. Models already use 'export_to_domklik'.
                # No RenameField here to avoid state_forwards crash when old field doesn't exist.
            ],
        ),
    ]
