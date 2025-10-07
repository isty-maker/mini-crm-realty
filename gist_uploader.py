import json
import os

import requests

LOG_PATH = "/var/log/isty.pythonanywhere.com.error.log"
TOKEN = os.getenv("GITHUB_GIST_TOKEN")
GIST_ID_FILE = os.path.expanduser("~/.gist_id")

if not TOKEN:
    print("❌ Нет токена (GITHUB_GIST_TOKEN).")
    raise SystemExit(1)

if not os.path.exists(LOG_PATH):
    print(f"❌ Лог-файл не найден: {LOG_PATH}")
    raise SystemExit(1)

with open(LOG_PATH, "r", encoding="utf-8") as f:
    lines = f.readlines()[-300:]
content = "".join(lines)
headers = {"Authorization": f"token {TOKEN}"}

if os.path.exists(GIST_ID_FILE):
    with open(GIST_ID_FILE, "r", encoding="utf-8") as f:
        gist_id = f.read().strip()
    url = f"https://api.github.com/gists/{gist_id}"
    payload = {"files": {"error.log": {"content": content}}}
    r = requests.patch(url, headers=headers, data=json.dumps(payload))
    if r.status_code == 200:
        print("✅ Gist обновлён")
        print("RAW_URL:", r.json()["files"]["error.log"]["raw_url"])
    else:
        print("❌ Ошибка обновления:", r.status_code, r.text)
else:
    data = {"public": True, "files": {"error.log": {"content": content}}}
    r = requests.post("https://api.github.com/gists", headers=headers, data=json.dumps(data))
    if r.status_code == 201:
        gist = r.json()
        gist_id = gist["id"]
        with open(GIST_ID_FILE, "w", encoding="utf-8") as f:
            f.write(gist_id)
        print("✅ Gist создан!")
        print("RAW_URL:", gist["files"]["error.log"]["raw_url"])
    else:
        print("❌ Ошибка создания:", r.status_code, r.text)
