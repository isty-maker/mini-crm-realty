# Mini CRM Realty

## Установка
1. Убедитесь, что установлен **Python 3.12**.
2. Создайте и активируйте виртуальное окружение:
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   ```
3. Установите зависимости проекта:
   ```bash
   pip install -r requirements.txt -r requirements-extra.txt
   ```

## Запуск
1. Примените миграции базы данных:
   ```bash
   python manage.py migrate
   ```
2. Запустите локальный сервер разработки:
   ```bash
   python manage.py runserver
   ```

## Деплой на PythonAnywhere
Подробная инструкция доступна в [docs/deploy_pa_NEW.md](docs/deploy_pa_NEW.md).

## Экспорт данных
- В админке доступен экспорт по адресу `/panel/export/cian`.
- Сгенерированный файл выгрузки сохраняется в `media/feeds/cian.xml`.
