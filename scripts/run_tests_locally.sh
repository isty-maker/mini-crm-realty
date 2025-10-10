#!/usr/bin/env bash
set -euo pipefail

pip install -r requirements.txt -r requirements-dev.txt

python - <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "realcrm.settings")
__import__("django")
print("Django import OK")
PY

pytest -q
