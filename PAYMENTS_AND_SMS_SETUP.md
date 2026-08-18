# GameMarket v2.6 — реальные платежи, выплаты и SMS

Эта версия добавляет реальные пополнения через YooKassa, выплаты продавцам по СБП через YooKassa Payouts и полноценное подтверждение телефона по SMS. Все секреты находятся только на backend.

## 1. Миграция PostgreSQL

Если база уже существует, после резервной копии и остановки backend один раз выполните:

```text
scripts/migrate_v2_6_payments.sql
```

Миграция:

- добавляет `users.withdrawable_balance`;
- добавляет `orders.buyer_withdrawable_spent` для точного возврата источника средств при споре;
- создаёт/дополняет `payment_deposits`;
- дополняет `withdrawal_requests` полями провайдера, idempotency, банка и ошибки;
- создаёт индексы для защиты от повторной обработки.

Существующий исторический баланс намеренно не становится автоматически доступным к выводу. После миграции выводимым считается новый заработок продавца. Если исторический заработок нужно перенести, его следует рассчитать по истории операций вручную и отдельно заполнить `withdrawable_balance`.

## 2. YooKassa — пополнение

В личном кабинете YooKassa получите `shopId` и секретный ключ магазина. На сервере заполните `.env`:

```env
PAYMENT_PROVIDER=yookassa
YOOKASSA_SHOP_ID=YOUR_SHOP_ID
YOOKASSA_SECRET_KEY=YOUR_SECRET_KEY
DEPOSIT_MIN_RUB=10
DEPOSIT_MAX_RUB=150000
PUBLIC_APP_URL=https://your-domain.ru
YOOKASSA_RETURN_URL=https://your-domain.ru/profile?payment_return=1
ANDROID_PAYMENT_RETURN_URL=https://your-domain.ru/payment-return
ALLOW_DEV_DEPOSITS=false
```

Web и Android не получают секретный ключ YooKassa. Backend создаёт платёж с idempotency key, клиент открывает `confirmation_url`, а баланс зачисляется только после подтверждения статуса через API YooKassa.

Для Android `return_url` должен оставаться обычным абсолютным HTTPS-адресом. В проект добавлена страница `/payment-return`: она предлагает пользователю вернуться в приложение через deep link `gamemarket://payment-return`. Даже если deep link не сработает, Android хранит ID последнего пополнения и синхронизирует его статус при возврате в приложение.

Настройте HTTPS webhook:

```text
https://your-domain.ru/payments/yookassa/webhook
```

События для пополнений:

```text
payment.succeeded
payment.canceled
```

## 3. YooKassa — выплаты по СБП

Выплаты подключаются в YooKassa отдельно. После активации получите идентификатор шлюза (agentId) и его секретный ключ:

```env
PAYOUT_PROVIDER=yookassa
YOOKASSA_PAYOUT_GATEWAY_ID=YOUR_GATEWAY_ID
YOOKASSA_PAYOUT_SECRET_KEY=YOUR_PAYOUT_SECRET
WITHDRAWAL_MIN_RUB=100
WITHDRAWAL_MAX_RUB=100000
REQUIRE_VERIFIED_FOR_WITHDRAWAL=true
WITHDRAWAL_VERIFICATION_POLICY=both
```

Для выплат добавьте в тот же webhook события:

```text
payout.succeeded
payout.canceled
```

Пользователь выбирает банк СБП, но номер телефона для автоматической выплаты берётся только из подтверждённого телефона его аккаунта. Реквизиты выплаты шифруются в БД. Пополненные пользователем деньги не становятся выводимыми: выводится только заработок продавца.

Текущая безопасная схема — заявка сначала резервирует сумму, затем администратор подтверждает выплату. После подтверждения backend создаёт payout в YooKassa. Это сохраняет ручной антифрод-контроль перед реальным переводом денег.

## 4. SMS.RU — подтверждение телефона

Создайте аккаунт SMS.RU, получите `api_id`, затем заполните:

```env
SMS_PROVIDER=smsru
SMSRU_API_ID=YOUR_SMSRU_API_ID
SMSRU_FROM=
SMS_TIMEOUT_SECONDS=15
OTP_DEV_ECHO=false
```

`SMSRU_FROM` можно оставить пустым, пока имя отправителя не согласовано. Код подтверждения генерируется backend, в БД хранится только HMAC-хэш. Действуют лимиты повторной отправки, количества попыток и запросов с IP.

Рекомендуемая production-политика:

```env
SELLER_VERIFICATION_POLICY=any
WITHDRAWAL_VERIFICATION_POLICY=both
PASSWORD_RESET_CHANNELS=email,phone
```

В Android на экране «Безопасность» теперь можно добавить номер, если его ещё нет, и сразу запросить SMS-код.

## 5. Production

Минимально:

```env
ENVIRONMENT=production
ALLOW_DEV_DEPOSITS=false
OTP_DEV_ECHO=false
MIGRATE_LEGACY_SCHEMA=false
PUBLIC_APP_URL=https://your-domain.ru
CORS_ORIGINS=https://your-domain.ru
SECRET_KEY=LONG_RANDOM_SECRET_32+_CHARS
CONTENT_ENCRYPTION_KEY=FERNET_KEY
```

Backend должен быть доступен по HTTPS. Android release должен использовать HTTPS API URL. Не помещайте `.env`, ключи YooKassa, SMS.RU, PostgreSQL или SMTP в APK или frontend JavaScript.

Отдельно согласуйте с YooKassa и бухгалтерией сценарий фискализации/чеков и юридическую модель маркетплейса: эти параметры зависят от договора, налогового режима и того, является ли пополнение авансом, оплатой услуги площадки или частью marketplace-сделки.

## 6. Проверка

1. Выполнить миграцию и запустить backend.
2. `GET /health` должен вернуть версию `2.6.0`.
3. `GET /balance/config` после входа должен показать `payment_configured=true` при заполненных ключах.
4. Создать тестовое пополнение, оплатить в тестовом режиме YooKassa и проверить, что `payment_deposits.status=succeeded`, а баланс увеличился ровно один раз.
5. Повторно отправить/обработать webhook — баланс не должен увеличиться второй раз.
6. Подтвердить email и телефон.
7. Завершить тестовую продажу — сумма `seller_earnings` должна попасть в `withdrawable_balance`.
8. Создать вывод по СБП. Сумма должна перейти в резерв.
9. Подтвердить заявку администратором и проверить payout/status/history.
10. Проверить Android: YooKassa возвращает браузер на HTTPS `/payment-return`, кнопка открывает `gamemarket://payment-return`, после возврата приложение синхронизирует баланс.
