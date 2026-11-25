"""Server-side SQLite and Django checks. Run with the production virtualenv."""

import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def backup(source, destination):
    if not source.is_file() or source.is_symlink():
        raise RuntimeError("Expected an existing SQLite file.")
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    with closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(destination)) as snapshot:
            original.backup(snapshot, pages=128)
            if snapshot.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise RuntimeError("SQLite backup failed its integrity check.")


def configure(database, domain, live):
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
    if live and database != expected:
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
    configured["default"]["NAME"] = str(database)


def migration_plan():
    from django.db import connection
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
    return "".join(f"{migration.app_label}.{migration.name}\n" for migration, _ in plan)


def django_stage(mode, database, plan_file, domain):
    import django
    from django.core.management import call_command

    configure(database, domain, live=mode == "apply")
    django.setup()
    if mode == "static-dry":
        call_command("collectstatic", dry_run=True, interactive=False, verbosity=0)
        return
    plan = migration_plan()
    print("Pending migration plan:", plan or "(empty)", sep="\n", flush=True)
    if mode == "plan":
        call_command("check", deploy=True)
        plan_file.write_text(plan, encoding="utf-8")
    else:
        if plan != plan_file.read_text(encoding="utf-8"):
            raise RuntimeError("Live migration plan changed after taking the backup.")
        if plan:
            call_command("migrate", interactive=False)
        if migration_plan():
            raise RuntimeError("Migrations still pending after apply.")


if __name__ == "__main__":
    if sys.argv[1] == "backup":
        backup(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        django_stage(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
