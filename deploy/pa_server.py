"""Server-side SQLite and Django checks. Run with the production virtualenv."""

import hashlib
import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def sqlite_file_check(snapshot):
    if snapshot.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
        raise RuntimeError("SQLite failed quick_check.")
    if snapshot.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("SQLite failed foreign_key_check.")


def backup(source, destination):
    if not source.is_file() or source.is_symlink():
        raise RuntimeError("Expected an existing SQLite file.")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    with closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)) as original:
        # page_count includes pages still in the source WAL. Account quota can
        # still be smaller than the free space reported by the filesystem.
        pages = original.execute("PRAGMA page_count").fetchone()[0]
        page_size = original.execute("PRAGMA page_size").fetchone()[0]
        if shutil.disk_usage(destination.parent).free < 2 * pages * page_size:
            raise RuntimeError("Insufficient filesystem space for the SQLite snapshot.")
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(destination)) as snapshot:
            original.backup(snapshot, pages=128)
            sqlite_file_check(snapshot)


def configure(database, domain, mode):
    # Script lives under deploy/, so put its own checkout first on the import path.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.environ["DJANGO_SETTINGS_MODULE"] = "realcrm.settings"
    from django.conf import settings
    from django.core.files.storage import FileSystemStorage, storages

    configured = settings.DATABASES
    expected = settings.BASE_DIR / "db.sqlite3"
    if (set(configured) != {"default"}
            or configured["default"]["ENGINE"] != "django.db.backends.sqlite3"
            or Path(configured["default"]["NAME"]).resolve() != expected):
        raise RuntimeError("Expected the project's default local SQLite configuration.")
    if mode == "apply" and database != expected:
        raise RuntimeError("Unexpected live SQLite path.")
    if (settings.DEBUG or domain not in settings.ALLOWED_HOSTS
            or f"https://{domain}" not in settings.CSRF_TRUSTED_ORIGINS):
        raise RuntimeError("Verify DEBUG, production host and trusted HTTPS origin.")
    if not all((settings.YANDEX_CLIENT_KEY_ID, settings.YANDEX_CLIENT_SECRET_KEY,
                settings.YANDEX_STORAGE_BUCKET_NAME)):
        raise RuntimeError("Missing Yandex Object Storage configuration.")
    static_root = settings.BASE_DIR / "staticfiles"
    static_storage = storages["staticfiles"]
    if (type(static_storage).__module__ != "django.contrib.staticfiles.storage"
            or not isinstance(static_storage, FileSystemStorage)
            or Path(static_storage.location).resolve() != static_root):
        raise RuntimeError("Expected Django local staticfiles storage.")
    if os.getenv("AUTO_APPLY_MIGRATIONS") == "1":
        raise RuntimeError("Disable request-time migrations before deploying.")
    configured["default"]["NAME"] = (
        f"{database.as_uri()}?mode=ro" if mode == "verify" else str(database)
    )
    configured["default"]["OPTIONS"] = {
        **configured["default"].get("OPTIONS", {}),
        "timeout": 5,
        "transaction_mode": "IMMEDIATE",
    }


def migration_plan(connection):
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    loader = executor.loader
    loader.check_consistent_history(connection)
    if loader.detect_conflicts():
        raise RuntimeError("Conflicting migration leaves.")
    known = set(loader.disk_migrations)
    for replacement in loader.replacements.values():
        known.update(replacement.replaces)
    unknown = set(loader.applied_migrations) - known
    if unknown:
        raise RuntimeError(f"Unreconciled applied migrations: {sorted(unknown)}")
    plan = executor.migration_plan(loader.graph.leaf_nodes())
    if any(backward for _, backward in plan):
        raise RuntimeError("Backward migration plans require manual recovery.")
    return executor, plan


def automatic_migration(plan):
    """Allow only one atomic and independent table creation."""
    from django.db import migrations, models
    from django.db.models import NOT_PROVIDED

    if len(plan) != 1:
        return False
    migration, backwards = plan[0]
    if (backwards or migration.atomic is not True or migration.replaces
            or type(migration).apply is not migrations.Migration.apply
            or len(migration.operations) != 1):
        return False
    operation = migration.operations[0]
    if type(operation) is not migrations.CreateModel:
        return False
    if operation.options or operation.bases != (models.Model,) or operation.managers:
        return False
    allowed_fields = {
        models.AutoField, models.BigAutoField, models.BooleanField, models.CharField,
        models.DateTimeField, models.DecimalField, models.IntegerField, models.TextField,
    }
    return all(
        type(field) in allowed_fields
        and field.default is NOT_PROVIDED
        and field.db_default is NOT_PROVIDED
        and not field.db_index
        and (not field.unique or field.primary_key)
        for _, field in operation.fields
    )


def reviewed_price_history(plan):
    """The reviewed PR #188 SQL may rehearse; its live use still needs downtime."""
    from django.conf import settings

    if len(plan) != 1:
        return False
    migration, _ = plan[0]
    active = getattr(settings, "MIGRATION_MODULES", {}).get("core", "core.migrations")
    name = {
        "core.migrations": "0014_price_history",
        "core.mig_current": "0002_price_history",
    }.get(active)
    if name is None or (migration.app_label, migration.name) != ("core", name):
        return False
    hashes = {
        "core/migrations/0014_price_history.py": "d290519b437014ee7211a127ea6bc930772e077b127f8d318ee734b2d5312884",
        "core/mig_current/0002_price_history.py": "16fcef0c57d0773a241c5cff42e650f88b36293a0830956c907e3a52b3e67ac5",
    }
    for path, expected in hashes.items():
        if active == "core.migrations" and path.startswith("core/mig_current/"):
            continue
        file = settings.BASE_DIR / path
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            return False
    return True


def describe_plan(connection, plan, sha):
    migrations = [f"{migration.app_label}.{migration.name}" for migration, _ in plan]
    if not plan:
        policy = "none"
    elif automatic_migration(plan):
        policy = "automatic"
    elif reviewed_price_history(plan):
        policy = "price-history"
    else:
        policy = "manual"
    with connection.cursor() as cursor:
        cursor.execute("SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name")
        schema = hashlib.sha256(json.dumps(cursor.fetchall()).encode()).hexdigest()
    return {"sha": sha, "migrations": migrations, "policy": policy, "schema": schema}


def verify_price_history(connection):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM core_property AS p
                WHERE NOT EXISTS (
                    SELECT 1 FROM core_pricehistory AS h
                    WHERE h.property_id = p.id AND h.kind = 'baseline' AND h.new_price IS p.price
                )
            )
        """)
        if cursor.fetchone()[0]:
            raise RuntimeError("Price-history snapshot is missing a matching baseline.")
        cursor.execute("""
            SELECT count(*) FROM sqlite_schema
            WHERE type = 'trigger' AND tbl_name = 'core_property'
              AND name IN ('core_price_history_insert', 'core_price_history_update')
        """)
        if cursor.fetchone()[0] != 2:
            raise RuntimeError("Price-history trigger invariant failed.")


def checked_migrate(connection, expected, allow_manual):
    from django.core.management import call_command

    def checked_plan():
        executor, plan = migration_plan(connection)
        if describe_plan(connection, plan, expected["sha"]) != expected:
            raise RuntimeError("SQLite schema, migration plan or policy changed since rehearsal.")
        return executor, plan

    if expected["policy"] == "automatic":
        # Enter a write transaction before comparing the plan. SQLite's
        # BEGIN IMMEDIATE serializes other writers until schema + record commit.
        # The executor deliberately omits pre/post_migrate signal handlers.
        with connection.schema_editor(atomic=True):
            executor, plan = checked_plan()
            executor.migrate(executor.loader.graph.leaf_nodes(), plan=plan)
    else:
        _, plan = checked_plan()
        if plan:
            if not allow_manual:
                raise RuntimeError("Migration rehearsal or apply requires explicit SHA approval.")
            try:
                call_command("migrate", interactive=False, verbosity=0)
            except Exception as exc:
                raise RuntimeError(f"Migration execution failed ({type(exc).__name__}).") from None
    if migration_plan(connection)[1]:
        raise RuntimeError("Migrations still pending after migrate.")


def django_stage(mode, database, plan_file, domain, sha, approved):
    import django
    from django.core.management import call_command
    from django.db import connection

    configure(database, domain, mode)
    django.setup()
    if mode == "static-dry":
        call_command("collectstatic", dry_run=True, interactive=False, verbosity=0)
        return

    if mode == "rehearse":
        _, plan = migration_plan(connection)
        expected = describe_plan(connection, plan, sha)
        print(f"Migration policy: {expected['policy']}; plan: {', '.join(expected['migrations']) or '(empty)'}", flush=True)
        if expected["policy"] == "manual" and not approved:
            raise RuntimeError("Unknown migrations require SHA-specific approval even for rehearsal.")
        checked_migrate(connection, expected, allow_manual=True)
        connection.ensure_connection()
        sqlite_file_check(connection.connection)
        if expected["policy"] == "price-history":
            verify_price_history(connection)
        call_command("check", deploy=True)
        plan_file.write_text(json.dumps(expected), encoding="utf-8")
        return

    expected = json.loads(plan_file.read_text(encoding="utf-8"))
    if expected["sha"] != sha:
        raise RuntimeError("Migration manifest has a different target SHA.")
    if mode == "verify":
        _, plan = migration_plan(connection)
        if describe_plan(connection, plan, sha) != expected:
            raise RuntimeError("SQLite schema, migration plan or policy changed since rehearsal.")
    elif mode == "apply":
        checked_migrate(connection, expected, allow_manual=approved)
    else:
        raise RuntimeError("Unknown deployment stage.")


if __name__ == "__main__":
    try:
        if sys.argv[1] == "backup":
            backup(Path(sys.argv[2]), Path(sys.argv[3]))
        else:
            mode, database, plan_file, domain, sha, approval = sys.argv[1:]
            django_stage(mode, Path(database), Path(plan_file), domain, sha, approval == "yes")
    except Exception as exc:
        # SQLite/Django exceptions can embed row values. Surface only the type
        # for unexpected failures and keep credentials and data out of logs.
        if type(exc) is RuntimeError:
            sys.exit(str(exc))
        sys.exit(f"Deployment check failed ({type(exc).__name__}).")
