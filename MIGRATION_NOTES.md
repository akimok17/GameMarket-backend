# v2.6.0

Run `scripts/migrate_v2_6_payments.sql` after the v2.5 migration. It adds real-payment deposit metadata, seller-only withdrawable balance, payout provider fields, and exact withdrawable-source tracking for order refunds. The script is repeatable and can complete an earlier manually-created `payment_deposits` table.

> **v2.3.1 hotfix:** legacy `disputes` tables are migrated for Order Room compatibility.

# GameMarket migration notes

## v2.3.0

Order Room добавляет две новые сущности:

- `order_messages` — переписка строго в контексте конкретной сделки;
- `order_events` — неизменяемая для пользователей история событий сделки.

В `orders` добавлены:

- `delivery_secret` — зашифрованные данные ручной/автоматической выдачи;
- `product_title_snapshot` и `product_category_snapshot` — заказ сохраняет, что именно было куплено, даже если объявление позже изменилось;
- `last_activity_at` — сортировка/активность сделки.

Для существующей PostgreSQL БД выполни `scripts/migrate_v2_3.sql` после остановки backend. Скрипт повторяемый и не удаляет строки.

## v2.2.0

Добавлены подтверждение email/телефона, поддержка, уведомления и дополнительные поля безопасности пользователя.

## Legacy database

SQLAlchemy `Base.metadata.create_all()` создаёт отсутствующие таблицы, но не обновляет структуру уже существующих таблиц. Поэтому при переходе между версиями используй SQL migration/в дальнейшем Alembic, а не только `create_all()`.
