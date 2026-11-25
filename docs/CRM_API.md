# CRM API v1

API работает только по HTTPS при включённом `CRM_REQUIRE_STAFF_LOGIN`. Используйте `Authorization: Bearer <ключ>`. Сессия браузера и параметры URL не дают доступа. Ключ привязан к активному сотруднику и имеет права чтения либо чтения и записи. Ответы имеют `Cache-Control: no-store`. Отключение сотрудника блокирует его ключи.

Из закрытой операторской консоли `python manage.py crm_api_key <сотрудник> --label <имя>` выдаёт ключ чтения. Добавьте `--write` для записи. Ключ показывается один раз. `--revoke <id>` отзывает ключ, а `--rotate <id>` атомарно выдаёт новый с прежними правами. Секреты не передавайте через общий терминал, командную строку в истории, тикеты или логи. Храните ключ в секретном хранилище клиента. Webhook, SQL, публикация, расходы и удаление не входят в v1.

## Маршруты

| Метод и путь | Запрос и результат |
|---|---|
| GET /api/v1/objects/ | `q`, `status`, `page`, `page_size` (1–100). Возвращает `items[{id,address,status}]`, страницу, размер и количество. |
| GET /api/v1/objects/{id}/ | `id`, `version`, `listing`, `workspace`, `collections`. Версия также в `ETag`. |
| POST /api/v1/objects/ | `{"listing":{...}}`. Новый черновик, обе выгрузки выключены. Требует `Idempotency-Key`. Нормализованное совпадение адреса возвращает 409 с ID существующих объектов, поэтому разные объявления по одному адресу нужно различить при согласовании паспорта. |
| PATCH /api/v1/objects/{id}/ | `{"listing":{...},"workspace":{"status":{...},"terms":{...},"legal":{...}}}`. Любые группы могут отсутствовать. Требует `If-Match` из GET. Изменение нескольких групп атомарно. |
| GET /api/v1/objects/{id}/{collection}/ | Список связанных записей и версия объекта. |
| POST /api/v1/objects/{id}/{collection}/ | Создаёт одну запись. Тело — поля записи. Требует `Idempotency-Key` и версию объекта в `If-Match`. |
| GET /api/v1/objects/{id}/{collection}/{record_id}/ | Читает одну связанную запись с её собственной версией. |
| PATCH /api/v1/objects/{id}/{collection}/{record_id}/ | Меняет переданные поля записи. Требует её версию. |
| GET /api/v1/objects/{id}/changes/ | Последние 100 событий с автором, временем, источником и именами изменённых полей. |
| GET /api/v1/document-types/ | Справочник `{id,slug,title}` для поля `document_type`. |

`HEAD` поддерживается на маршрутах чтения. Коллекции `files`, `documents`, `bases`, `owners` и `notes` изменяются по стабильным ID. Пропуск коллекции или поля ничего не удаляет. Ссылку оригинала сначала сохраните в `files`, затем передайте ID файла в `documents.original`. Связи с другим объектом запрещены. ID автора и даты создания заметки вычисляются сервером.

### Поля, типы и перечисления

Канонический разрешённый список публичных полей находится в [`LISTING_FIELDS`](../crm_api/records.py). Категория, операция и поля подтипов разрешены при создании. Основные типы: `flat`, `room`, `house`, `land`, `commercial`, `garage`. Операции: `sale`, `rent_long`, `rent_daily`. Валюты: `rur`, `usd`, `eur`. Состояние, архив и флаги выгрузки видны в ответе и запрещены для записи. Площадь и цена передаются десятичными строками, например `"60.25"`. Счётчики и ID — JSON integer. Булевы поля — `true` или `false`. Дата — `YYYY-MM-DD`, дата и время — ISO 8601. `null` допустим только у nullable-полей модели, пустая строка — у необязательного текста.

Канонический список рабочих и связанных полей находится в [`SCOPES`](../core/private_records.py). Коды сохраняемых перечислений определены в [моделях](../core/workspace_models.py). Рабочий статус: `unknown`, `preparing`, `active`, `paused`, `deposit`, `closing`, `sold`, `let`, `renewal`, `expired`, `terminated`. Документ: применимость `unknown`, `not_needed`, `required`; наличие `unknown`, `missing`, `present`; проверка `unknown`, `checked`, `issues`. При проверке документа укажите `checked_on`. Основания: `unknown`, `purchase`, `inheritance`, `gift`, `privatization`, `participation`, `other`. Владельцы имеют `name`, `share_numerator` и `share_denominator`. Заметка принимает только `text`. Публикация не меняется при изменении рабочего статуса.

### Версии, предпросмотр и повтор

Передайте `?dry_run=1` с телом POST или PATCH, чтобы получить старое и предлагаемое значение и предупреждения без записи. Для PATCH и связанных записей возвращается версия снимка. При сохранении используйте её в `If-Match: "<версия>"`, включая кавычки. При 409 прочитайте объект и подтвердите изменения заново. У POST создания объекта версии ещё нет, его защищают проверка адреса и ключ идемпотентности. Повтор с тем же ключом и тем же JSON возвращает тот же ID и `Idempotency-Replayed: true`; тело показывает текущее состояние. Ключ действует в пределах API-ключа и маршрута. Другое тело с тем же ключом возвращает 409.

Ошибки имеют форму `{"error":{"code":"…","message":"…","fields":…}}`. Успехи: 200 и 201. Ошибки: 400 запрос, 401 ключ, 403 доступ или HTTPS, 404 запись, 405 метод, 409 конфликт или возможный дубль, 413 размер, 415 тип содержимого, 422 поля, 428 нет версии. Ответ конфликта содержит текущие данные и версию там, где их можно повторно получить после перепроверки.

## Пример

Используйте переменную из закрытого хранилища. Ниже ключ и хост вымышлены.

```bash
crm_url='https://example.invalid/api/v1/objects/'
crm_token='synthetic-example-not-a-real-key'
curl -sS -H "Authorization: Bearer $crm_token" "$crm_url"
curl -sS -X POST -H "Authorization: Bearer $crm_token" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: demo-import-1' \
  --data '{"listing":{"address":"Учебный объект","category":"flat","operation":"sale","flat_type":"apartment","total_area":"60.25","currency":"rur"}}' \
  "$crm_url"
curl -si -H "Authorization: Bearer $crm_token" "${crm_url}1/"
curl -sS -X PATCH -H "Authorization: Bearer $crm_token" \
  -H 'Content-Type: application/json' --data '{"listing":{"price":"6350000.25"}}' \
  "${crm_url}1/?dry_run=1"
```

После dry-run повторите PATCH без параметра и с заголовком `If-Match`, затем повторите GET и проверьте карточку. [Синтетический паспорт](examples/crm-api-passport.json) разложен на создание, общую правку и массивы связанных записей. Воспроизводимый тест `python manage.py test crm_api.tests.test_api` преобразует `documents[].type` в ID справочника, а `documents[].file` в ID ранее созданного файла. Тест проводит dry-run, запись, повтор, сравнение с карточкой, конфликт ручной правки и проверки обоих XML.
