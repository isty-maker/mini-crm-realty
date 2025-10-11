#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv || true
source .venv/bin/activate
python -m pip install -U pip wheel
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
if [[ $# -gt 0 ]]; then
  pytest -q "$@"
else
  pytest -q
fi
