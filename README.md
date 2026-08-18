## v2.6.0 — real payments and payouts

- Real YooKassa balance deposits with server-side idempotency and authoritative webhook verification.
- Seller earnings are tracked separately as withdrawable funds; user top-ups cannot be cashed out.
- YooKassa Payouts integration for SBP withdrawals using the verified account phone and selected bank.
- Withdrawal destinations are encrypted at rest and user-facing API responses are masked.
- Web profile finance UI was rebuilt for responsive deposit/withdrawal flows.
- SMS phone verification remains shared by web/Android and now has a more direct mobile setup flow.
- Existing PostgreSQL databases must run `scripts/migrate_v2_6_payments.sql`.
- Setup: `PAYMENTS_AND_SMS_SETUP.md`.

## v2.5.0

Production account verification was upgraded in v2.5.0: email + SMS confirmation, password recovery through either channel, configurable seller/withdrawal policies, per-IP OTP limits, and shared flows for web/Android. See `PRODUCTION_VERIFICATION_SETUP.md`.


SMTP TLS version can now be pinned with `SMTP_TLS_VERSION=tls1_2` for Mail.ru/VPN/OpenSSL compatibility.

> **v2.3.1 hotfix:** legacy `disputes` tables are migrated for Order Room compatibility.

# GameMarket v2.3.0 — Order Room

FastAPI + PostgreSQL/SQLite + статический frontend для маркетплейса цифровых товаров.
Главное изменение v2.3 — полноценная **страница сделки** после оплаты: `/order/{id}`.

## Что есть в v2.3

- регистрация, JWT, подтверждение email/телефона, восстановление и смена пароля;
- роли покупатель / продавец / администратор;
- товары, категории, поиск, сортировка, остатки, избранное;
- автоматическая и ручная выдача цифровых товаров;
- шифрование цифровых единиц и данных выдачи;
- внутренний баланс, история операций, заявки на вывод;
- защищённая логика заказа и комиссия площадки;
- **Order Room** — отдельная страница каждого заказа;
- realtime WebSocket-чат строго внутри конкретного заказа;
- online/presence, «печатает…», доставлено/прочитано;
- приватные изображения-вложения в чат (доступны только участникам заказа/админу);
- системные сообщения GameMarket и полный timeline сделки;
- защищённый блок выданного товара;
- ручная выдача продавцом и автоматическая выдача ключей;
- подтверждение получения покупателем;
- автозавершение по таймеру;
- спор прямо со страницы сделки;
- поддержка с автоматической привязкой `order_id`;
- отзывы только после завершённой сделки;
- статистика продавца: успешность, споры, среднее время ответа/выполнения;
- уведомления со ссылкой непосредственно на страницу заказа;
- read-only доступ администратора к Order Room для разбора спорных ситуаций.

## Обновление с v2.2.0

Для существующей PostgreSQL базы **один раз** выполни:

```text
scripts/migrate_v2_3.sql
```

через pgAdmin Query Tool. Скрипт не удаляет старые данные. Он добавляет:

- `orders.delivery_secret`;
- snapshot названия/категории товара;
- `orders.last_activity_at`;
- таблицу `order_messages`;
- таблицу `order_events`;
- индексы;
- базовый timeline для уже существующих заказов.

После успешной миграции можно оставить:

```env
MIGRATE_LEGACY_SCHEMA=false
CREATE_TABLES_ON_STARTUP=true
```

`create_all()` создаст полностью новые таблицы, но не добавляет поля в старые таблицы — поэтому SQL-миграция для существующей базы обязательна.

## Запуск

```powershell
cd D:\gamemarket_v2.3.0\gamemarket_v2.3.0
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Если виртуальное окружение лежит уровнем выше, активируй именно его путь.

После запуска:

- Маркет: `http://127.0.0.1:8000/`
- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`
- Сделка: `http://127.0.0.1:8000/order/ID`
- Поддержка: `http://127.0.0.1:8000/support`

## Новый Order Room API

```text
GET  /order-room/{order_id}
POST /order-room/{order_id}/ws-token
POST /order-room/{order_id}/messages
POST /order-room/{order_id}/read
POST /order-room/{order_id}/attachments
GET  /order-room/{order_id}/attachments/{filename}
WS   /ws/orders/{order_id}?token=<short-lived-token>
```

WebSocket использует отдельный короткоживущий токен, а не основной access token в URL.

## Приватность вложений

Файлы чата не кладутся в публичный `/static`. Они находятся в:

```text
storage/order_attachments/<order_id>/
```

и выдаются только через защищённый endpoint после проверки, что пользователь является покупателем, продавцом или администратором заказа.

## Production

Перед публичным запуском обязательно:

- `ENVIRONMENT=production`;
- `ALLOW_DEV_DEPOSITS=false`;
- `OTP_DEV_ECHO=false`;
- сильный случайный `SECRET_KEY`;
- отдельный `CONTENT_ENCRYPTION_KEY`;
- HTTPS;
- PostgreSQL;
- Alembic вместо startup-миграций;
- настоящий платежный provider + проверенные webhooks + idempotency;
- rate limit на auth/chat/payment/verification;
- антивирус/сканирование загружаемых файлов при расширении типов вложений;
- object storage для вложений при масштабировании на несколько серверов;
- Redis/pub-sub для WebSocket presence/chat при нескольких workers;
- резервные копии БД, централизованные логи и мониторинг.

## Важное про WebSocket

Текущий connection manager рассчитан на один процесс Uvicorn. Для локального запуска это нормально. Если запустить несколько workers/серверов, realtime нужно вынести в Redis pub/sub (или аналог), иначе разные workers не будут видеть подключения друг друга.

## v2.6.0 — real balance top-up, payouts and polished verification

The backend now supports YooKassa balance top-ups with idempotency and authoritative webhook verification, seller-only withdrawable earnings, SBP payout requests, encrypted payout destinations, and payment/payout status synchronization. Run `scripts/migrate_v2_6_payments.sql` once on an existing PostgreSQL database.

Phone verification already uses the same OTP flow as email. To enable real SMS delivery, configure `SMS_PROVIDER=smsru` and `SMSRU_API_ID` (or another supported SMS provider) in backend `.env`. Never place SMS or YooKassa secrets in the web frontend or Android app.
