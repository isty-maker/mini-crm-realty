from importlib import import_module

from django.conf import settings
from django.db import migrations


class Migration(import_module("core.migrations.0016_workspace_audit").Migration):
    dependencies = [("core", "0003_private_workspace"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
