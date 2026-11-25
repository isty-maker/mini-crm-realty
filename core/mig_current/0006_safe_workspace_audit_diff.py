from importlib import import_module


class Migration(import_module("core.migrations.0018_safe_workspace_audit_diff").Migration):
    dependencies = [("core", "0005_workspace_record_currency")]
