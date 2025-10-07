"""Upload the latest project error log to a persistent GitHub Gist.

This script is designed for the PythonAnywhere deployment where direct log
downloads are not possible. It reads the last 300 lines from the project's
error log, then creates or updates a public GitHub Gist whose raw URL can be
shared with the team (and the assistant) for quick debugging.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import requests
import subprocess


LOG_PATH = Path("/var/log/isty.pythonanywhere.com.error.log")
TOKEN = os.getenv("GITHUB_GIST_TOKEN")
GIST_ID_FILE = Path.home() / ".gist_id"
GIST_FILENAME = "error.log"
LOG_TARGET = "/home/isty/mini-crm-realty/docs/logs/latest-error.log"


def _read_log_tail(path: Path, max_lines: int = 300) -> str:
    """Return the last *max_lines* of *path* joined into a single string."""

    with path.open("r", encoding="utf-8") as f:
        lines = f.readlines()[-max_lines:]
    return "".join(lines)


def _print_missing_token() -> None:
    print("❌ Нет токена (GITHUB_GIST_TOKEN).")


def _print_missing_log(path: Path) -> None:
    print(f"❌ Лог-файл не найден: {path}")


def _print_update_error(response: requests.Response) -> None:
    print("❌ Ошибка обновления:", response.status_code, response.text)


def _print_create_error(response: requests.Response) -> None:
    print("❌ Ошибка создания:", response.status_code, response.text)


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"token {token}"}


def _update_gist(gist_id: str, content: str, token: str) -> None:
    url = f"https://api.github.com/gists/{gist_id}"
    payload: Dict[str, Any] = {"files": {GIST_FILENAME: {"content": content}}}
    response = requests.patch(url, headers=_headers(token), data=json.dumps(payload))
    if response.status_code == 200:
        print("✅ Gist обновлён")
        print("RAW_URL:", response.json()["files"][GIST_FILENAME]["raw_url"])
    else:
        _print_update_error(response)


def _create_gist(content: str, token: str) -> None:
    payload: Dict[str, Any] = {
        "public": True,
        "files": {GIST_FILENAME: {"content": content}},
    }
    response = requests.post(
        "https://api.github.com/gists",
        headers=_headers(token),
        data=json.dumps(payload),
    )
    if response.status_code == 201:
        gist = response.json()
        gist_id = gist["id"]
        GIST_ID_FILE.write_text(gist_id, encoding="utf-8")
        print("✅ Gist создан!")
        print("RAW_URL:", gist["files"][GIST_FILENAME]["raw_url"])
    else:
        _print_create_error(response)


def main() -> None:
    if not TOKEN:
        _print_missing_token()
        raise SystemExit(1)

    if not LOG_PATH.exists():
        _print_missing_log(LOG_PATH)
        raise SystemExit(1)

    content = _read_log_tail(LOG_PATH)

    if GIST_ID_FILE.exists():
        gist_id = GIST_ID_FILE.read_text(encoding="utf-8").strip()
        if gist_id:
            _update_gist(gist_id, content, TOKEN)
        else:
            # No ID recorded yet, create a new gist instead of failing silently.
            _create_gist(content, TOKEN)
    else:
        _create_gist(content, TOKEN)

    os.makedirs(os.path.dirname(LOG_TARGET), exist_ok=True)
    with open(LOG_TARGET, "w", encoding="utf-8") as f:
        f.write(content)

    try:
        subprocess.run(["git", "add", LOG_TARGET], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"update log {datetime.now().isoformat()}"],
            check=True,
        )
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("✅ Лог обновлён и отправлен в репозиторий.")
    except subprocess.CalledProcessError as e:
        print("⚠️ Ошибка при git push:", e)


if __name__ == "__main__":
    main()
