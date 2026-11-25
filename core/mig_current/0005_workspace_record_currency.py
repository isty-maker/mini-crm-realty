from importlib import import_module


class Migration(import_module("core.migrations.0017_workspace_record_currency").Migration):
    dependencies = [("core", "0004_workspace_audit")]
