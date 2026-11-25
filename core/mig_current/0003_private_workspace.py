from importlib import import_module

from django.conf import settings
from django.db import migrations


PrivateWorkspaceMigration = import_module("core.migrations.0015_private_workspace").Migration


class Migration(PrivateWorkspaceMigration):
    dependencies = [
        ("core", "0002_price_history"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
