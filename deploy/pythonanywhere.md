# Деплой на PythonAnywhere (пошагово, бесплатно)

## 1. Подготовка кода локально (один раз)
- `git pull` (обновить код)
- (если нужно) `python -m venv .venv && .venv\Scripts\activate` (Windows) / `source .venv/bin/activate` (macOS/Linux)
- `pip install -r requirements.txt`
- `python manage.py collectstatic` (создаст папку `staticfiles/`)
- Закоммить/запушь обновления (если были).

## 2. Создание приложения на PythonAnywhere
- Зарегистрируйся/зайди на pythonanywhere.com
- Вкладка **Web** → **Add a new web app** → **Manual configuration** → Python 3.12 (или твоя версия).
- На странице приложения:
  - **Source code**: укажи путь к клонированному репо (например `/home/<username>/mini-crm-realty`)
  - **Virtualenv**: укажи путь к твоему виртуальному окружению (например `/home/<username>/.virtualenvs/mini-crm-realty`):
    * Если окружение не создано на сервере — создай в Bash-консоли:
      `python3.12 -m venv ~/.virtualenvs/mini-crm-realty`
      `~/.virtualenvs/mini-crm-realty/bin/pip install -r /home/<username>/mini-crm-realty/requirements.txt`
  - **WSGI configuration file**: открой и замени содержимое на:
    ```
    import os, sys
    from pathlib import Path

    BASE_DIR = Path("/home/<username>/mini-crm-realty")
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "realcrm.settings")

    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()
    ```
    (Поменяй `<username>` на свой логин PA.)

## 3. Где вписать домен и переменные окружения на PythonAnywhere

```
Web → Environment variables:
  DEBUG=False
  ALLOWED_HOSTS=<username>.pythonanywhere.com
  CSRF_TRUSTED_ORIGINS=https://<username>.pythonanywhere.com
  SITE_BASE_URL=https://<username>.pythonanywhere.com
  SHARED_KEY=kontinent  # замени при необходимости

Static files:
  /static/ → /home/<username>/mini-crm-realty/staticfiles
  /media/  → /home/<username>/mini-crm-realty/media

После git pull на сервере:
  workon mini-crm-realty  # или source venv/bin/activate
  cd ~/mini-crm-realty
  pip install -r requirements.txt
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
Затем Web → Reload.
```

## 4. Переменные окружения
- Во вкладке **Web** → раздел **Environment variables**:
  - Добавь:
    - `DEBUG` → `False`
    - `ALLOWED_HOSTS` → `<username>.pythonanywhere.com`
    - `CSRF_TRUSTED_ORIGINS` → `https://<username>.pythonanywhere.com`
    - `SITE_BASE_URL` → `https://<username>.pythonanywhere.com`
    - `SHARED_KEY` → `kontinent` (или свой)
- Сохрани.

## 5. Static & Media на PA
- Вкладка **Web** → секция **Static files**:
  - URL: `/static/` → Path: `/home/<username>/mini-crm-realty/staticfiles`
  - URL: `/media/`  → Path: `/home/<username>/mini-crm-realty/media`
- Нажми **Save**.

## 6. Миграции и сборка статики на сервере
- Открой **Bash console** на PA:
  ```
  workon mini-crm-realty        # активировать venv (если называл по-другому — подставь своё имя)
  cd ~/mini-crm-realty
  pip install -r requirements.txt
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
  ```
- Вернись во вкладку **Web** и нажми **Reload** (перезапустить приложение).

## 7. Проверка
- Открой `https://<username>.pythonanywhere.com/healthz` — должно показать `ok`.
- Открой `https://<username>.pythonanywhere.com/panel/` — должна открыться панель.
- Экспорт: `https://<username>.pythonanywhere.com/panel/export/cian` → отдаёт XML; файл также пишется в `/home/<username>/mini-crm-realty/media/feeds/cian.xml`.

## 8. Обновления кода в дальнейшем
- На сервере в Bash-консоли:
  ```
  cd ~/mini-crm-realty
  git pull
  workon mini-crm-realty
  pip install -r requirements.txt          # если менялись зависимости
  python manage.py migrate --noinput       # если появились миграции
  python manage.py collectstatic --noinput # если менялись статики
  ```
- Во вкладке **Web** нажми **Reload**.
- Готово — изменения на сайте.
