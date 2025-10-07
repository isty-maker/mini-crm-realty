# Развертывание на PythonAnywhere

## Подготовка
- Зарегистрируйте бесплатный аккаунт на [PythonAnywhere](https://www.pythonanywhere.com/).
- Откройте консоль Bash: **Dashboard → Open Web tab → Bash console**.

## Клонирование проекта и установка зависимостей
```bash
git clone https://github.com/isty-maker/mini-crm-realty.git
cd mini-crm-realty
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-extra.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

## Настройка веб-приложения
1. На вкладке **Web** создайте приложение: **Add a new web app → Manual configuration (Python 3.12)**.
2. Укажите виртуальное окружение: `/home/<login>/mini-crm-realty/venv`.
3. В разделе **Code** установите `realcrm.settings` как Django settings module.
4. В **Static files** добавьте:
   - URL: `/static/` → путь: `/home/<login>/mini-crm-realty/staticfiles`
   - URL: `/media/` → путь: `/home/<login>/mini-crm-realty/media`

## Переменные окружения (Web → Environment variables)
```
DEBUG=False
ALLOWED_HOSTS=<login>.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://<login>.pythonanywhere.com
SITE_BASE_URL=https://<login>.pythonanywhere.com
```

## Автовыгрузка логов в GitHub Gist
1. Добавьте токен в `~/.bashrc`:
   ```bash
   echo 'export GITHUB_GIST_TOKEN="ghp_ВАШ_ТОКЕН"' >> ~/.bashrc
   source ~/.bashrc
   ```
2. Запустите скрипт один раз, чтобы создать Gist и получить постоянную ссылку:
   ```bash
   cd ~/mini-crm-realty
   source venv/bin/activate
   python gist_uploader.py
   ```
3. Настройте крон-задачу, которая будет обновлять Gist каждые 10 минут:
   ```bash
   crontab -e
   ```
   Добавьте строку:
   ```
   */10 * * * * cd /home/<login>/mini-crm-realty && source venv/bin/activate && python gist_uploader.py > /home/<login>/gist_update.log 2>&1
   ```
   В консоль будут выводиться сообщения вида `✅ Gist обновлён` и постоянный `RAW_URL`, который можно использовать для просмотра актуальных логов.

## Завершение
1. Нажмите **Reload** на вкладке **Web**.
2. Проверьте админку: `https://<login>.pythonanywhere.com/admin/`.
3. Убедитесь, что фиды доступны: `https://<login>.pythonanywhere.com/media/feeds/cian.xml`.
