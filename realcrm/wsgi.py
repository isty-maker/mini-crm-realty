"""
WSGI config for realcrm project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import re
import subprocess

from django.conf import settings

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'realcrm.settings')

application = get_wsgi_application()


# Capture the revision when the worker loads. Reading HEAD per request could
# report the new checkout from a worker that still serves the previous code.
try:
    revision = subprocess.check_output(
        ["/usr/bin/git", "-C", str(settings.BASE_DIR), "rev-parse", "--verify", "HEAD"],
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=3,
    ).strip()
except (OSError, subprocess.SubprocessError):
    revision = ""
settings.APP_REVISION = revision if re.fullmatch(r"[0-9a-f]{40}", revision) else ""
