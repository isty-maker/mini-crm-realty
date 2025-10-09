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
- Укажите публичный базовый URL для медиа в `.env`:
  ```env
  FEED_PUBLIC_BASE_URL=https://example.com
  ```
- В админке доступен экспорт по адресу `/panel/export/cian`.
- Для локальной генерации выполните:
  ```bash
  python manage.py generate_cian_feed
  ```
  Команда сохранит XML в `media/feeds/cian.xml` и при необходимости выведет его в stdout (флаг `--stdout`).
- После генерации откройте `media/feeds/cian.xml` и убедитесь, что ссылки на фото (`<FullUrl>`) абсолютные и доступны в браузере.
