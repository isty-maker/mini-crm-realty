import os
import logging
from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import OperationalError, ProgrammingError

log = logging.getLogger(__name__)

def _has_unapplied_migrations(alias: str = "default") -> bool:
    try:
        connection = connections[alias]
        connection.prepare_database()
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        return bool(plan)
    except (OperationalError, ProgrammingError):
        return True
    except Exception as e:
        log.warning("auto_migrate: failed to check migrations: %s", e)
        return False

def auto_migrate_once_if_needed() -> None:
    """
    Apply pending migrations once at startup when DEBUG is True or env AUTO_MIGRATE=1;
    otherwise do nothing.
    """
    try:
        enabled = os.environ.get("AUTO_MIGRATE", "0") == "1" or bool(getattr(settings, "DEBUG", False))
        if not enabled:
            return
        if not _has_unapplied_migrations("default"):
            return
        log.warning("auto_migrate: unapplied migrations detected -> applying…")
        call_command("migrate", interactive=False, run_syncdb=True, verbosity=1)
        log.warning("auto_migrate: migrations applied")
    except Exception as e:
        log.error("auto_migrate: migrate failed: %s", e)
