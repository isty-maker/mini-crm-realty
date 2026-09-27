# Руководство по настройке Yandex Object Storage и деплою на PythonAnywhere

## Часть 1. Ручные действия в Yandex Cloud

1. Зайдите в консоль управления **Yandex Cloud**: [https://console.cloud.yandex.ru](https://console.cloud.yandex.ru).
2. Выберите или создайте **Каталог** (Folder).
3. Перейдите в раздел **Object Storage** и нажмите **Создать бакет**:
   - **Имя бакета:** Укажите уникальное имя, например `realcrm-media-storage`.
   - **Максимальный размер:** По умолчанию или укажите желаемый лимит.
   - **Доступ к объектам:** В настройках доступа включите **Публичный доступ на чтение объектов** (Read objects).
4. Перейдите в раздел **Сервисные аккаунты** (Service Accounts) в Вашем каталоге:
   - Нажмите **Создать сервисный аккаунты**.
   - Назовите его, например, `sa-realcrm-storage`.
   - Назначьте роль `storage.editor`.
5. Откройте созданный сервисный аккаунт и нажмите **Создать статический ключ доступа** (Static Access Key):
   - Сохраните появившиеся значения: **Идентификатор ключа (Key ID)** и **Секретный ключ (Secret Key)**.

---

## Часть 2. Настройка на PythonAnywhere

1. Перейдите в консоль Bash на **PythonAnywhere**.
2. Перейдите в директорию вашего проекта:
   ```bash
   cd ~/realcrm  # или имя вашей папки проекта
   ```
3. Откройте или создайте файл `.env`:
   ```bash
   nano .env
   ```
4. Добавьте в `.env` следующие переменные с ключами из Части 1:
   ```env
   YANDEX_CLIENT_KEY_ID=ваш_идентификатор_ключа
   YANDEX_CLIENT_SECRET_KEY=ваш_секретный_ключ
   YANDEX_STORAGE_BUCKET_NAME=realcrm-media-storage
   YANDEX_STORAGE_REGION=ru-central1
   YANDEX_S3_ENDPOINT_URL=https://storage.yandexcloud.net
   ```
5. Активируйте виртуальное окружение и установите новые зависимости:
   ```bash
   workon venv  # или source venv/bin/activate
   pip install -r requirements.txt
   ```
6. Выполните команду переноса существующих фотографий в Yandex Object Storage:
   ```bash
   python manage.py migrate_photos_to_yandex
   ```
   *Команда скопирует все фото в облако Яндекса, сверит размеры и пропустит дубли при повторном запуске.*
7. Выполните генерацию свежих XML-фидов в Yandex Object Storage:
   ```bash
   python manage.py generate_cian_feed
   ```
8. В интерфейсе PythonAnywhere перейдите на вкладку **Web** и нажмите зелёную кнопку **Reload** (Перезапустить веб-приложение).

---

## Часть 3. Проверка и очистка локального диска PythonAnywhere

1. Проверьте отображение фотографий в панели управления CRM на сайте.
2. Откройте любое фото в браузере и убедитесь, что его адрес начинается с `https://storage.yandexcloud.net/realcrm-media-storage/photos/...`.
3. Зайдите в ЦИАН / Домклик и укажите новые прямые ссылки на фиды в Яндекс Облаке:
   - `https://storage.yandexcloud.net/realcrm-media-storage/feeds/cian.xml`
   - `https://storage.yandexcloud.net/realcrm-media-storage/feeds/domklik.xml`
4. Когда убедитесь, что всё работает идеально, вы можете очистить локальный дисковый бэкап фотографий на PythonAnywhere:
   ```bash
   python manage.py purge_local_media_backup --confirm
   ```
