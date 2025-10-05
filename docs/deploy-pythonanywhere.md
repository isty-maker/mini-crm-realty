# Deploy to PythonAnywhere (Free)

## 1) Clone & setup (Bash console on PythonAnywhere)

```bash
git clone https://github.com/isty-maker/mini-crm-realty.git
cd mini-crm-realty
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

## 2) Create Web app (Dashboard → Web → Add new web app → Manual config, Python 3.12)
- Virtualenv: `/home/<login>/mini-crm-realty/venv`
- WSGI file (click “open” and set):

```python
import sys, os
project = '/home/<login>/mini-crm-realty'
if project not in sys.path:
    sys.path.append(project)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'realcrm.settings')
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Static files:

- URL: `/static/` → Path: `/home/<login>/mini-crm-realty/staticfiles`
- URL: `/media/` → Path: `/home/<login>/mini-crm-realty/media`

## 3) Environment variables (Web → Environment)

```
DEBUG = False
ALLOWED_HOSTS = <login>.pythonanywhere.com
CSRF_TRUSTED_ORIGINS = https://<login>.pythonanywhere.com
SITE_BASE_URL = https://<login>.pythonanywhere.com
```

Then press **Reload** in the Web tab.

## 4) After each update (deploy steps)

```bash
cd ~/mini-crm-realty
source venv/bin/activate
git pull
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Then go to the Web tab and press **Reload**.

## Pages

- Panel: `https://<login>.pythonanywhere.com/panel/`
