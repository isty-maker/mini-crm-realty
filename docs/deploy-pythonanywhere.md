# Деплой на PythonAnywhere (Free)

## Требования
- Аккаунт на [PythonAnywhere](https://www.pythonanywhere.com/) (тариф Free).

## Установка кода и зависимостей
```bash
git clone https://github.com/isty-maker/mini-crm-realty.git
cd mini-crm-realty
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

## Настройка веб-приложения
1. В разделе **Web** нажмите **Add a new web app** → **Manual config** (Python 3.12).
2. Укажите виртуальное окружение: `/home/<login>/mini-crm-realty/venv`.
3. В **Static files** добавьте пары путей:
   - `/static/` → `/home/<login>/mini-crm-realty/staticfiles`
   - `/media/` → `/home/<login>/mini-crm-realty/media`
4. Проверьте WSGI-конфиг: используйте `realcrm.settings`.

## Переменные окружения (Web → Environment variables)
```
DEBUG=False
ALLOWED_HOSTS=<login>.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://<login>.pythonanywhere.com
SITE_BASE_URL=https://<login>.pythonanywhere.com
```

## Финальные шаги
1. Нажмите **Reload** в разделе **Web**.
2. Проверьте панель: `https://<login>.pythonanywhere.com/panel/`.
3. После генерации фида убедитесь, что файл доступен: `https://<login>.pythonanywhere.com/media/feeds/cian.xml`.

## Обновление после деплоя
```bash
cd ~/mini-crm-realty
source venv/bin/activate
git pull
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```
Затем снова нажмите **Reload** в разделе **Web**.
