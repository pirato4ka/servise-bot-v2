# Документация — Telegram Service Bot Final v3

**Версия:** 3.0 CryptoBot Edition  
**Дата:** 21.07.2026  
**Стек:** Python 3.11, aiogram 3.7, SQLite, aiocryptopay  
**Локализация:** User UI — українська, Admin UI — русский  

---

## 1. Обзор системы

Бот предназначен для конфиденциальной продажи услуг через Telegram. Ключевые принципы:

- **Анонимность:** Все ответы пользователю идут от имени бота, ID админов не светятся.
- **Доверие:** Премиум UI/UX, отсутствие спама, подтверждение заявки и договорная цена.
- **Монетизация:** Оплата через @CryptoBot бесконечными инвойсами (без срока годности).
- **CRM внутри Telegram:** Админ-чат выступает как helpdesk, тикеты создаются автоматически.

### Роли

1.  **Пользователь (клієнт)** — видит только украинский интерфейс, кнопки под полем ввода, анкету и счет на оплату.
2.  **Администратор** — любой участник админ-чата. Видит заявки, отвечает REPLY, подтверждает и выставляет цену, управляет услугами через `/admin`.

---

## 2. Архитектура

### 2.1 Диаграмма слоев

```
[ Telegram API ] 
      ↓
[ Middlewares: Throttling, AdminAutoRegister ]
      ↓
[ Routers: membership, reply_handler, confirm_payment, payment_check, admin_panel, start, services, questionnaire, user_chat ]
      ↓
[ Business Logic: cryptopay.py, formatter.py ]
      ↓
[ Data Layer: SQLite (users, services, tickets, invoices, admins, messages_log) ]
```

### 2.2 Компоненты

| Компонент | Файл | Ответственность |
|-----------|------|-----------------|
| Entry point | `app/bot.py` | init_db, регистрация роутеров, polling |
| Config | `app/config.py` | pydantic-settings, .env |
| DB | `app/database/db.py` | Создание таблиц, сид 3 услуг |
| CRUD | `app/database/crud.py` | Все запросы к БД |
| CryptoPay | `app/services/cryptopay.py` | Создание бесконечных инвойсов |
| User Flow | `handlers/start.py, services.py, questionnaire.py` | Выбор услуги, анкета |
| Free chat | `handlers/user_chat.py` | Форвард свободных сообщений юзера в тред заявки |
| Admin Reply | `handlers/admin/reply_handler.py` | REPLY из админ-чата -> юзеру |
| Admin Confirm | `handlers/admin/confirm_payment.py` | Подтвердить/Отклонить + ввод цены |
| Payment Check | `handlers/admin/payment_check.py` | Проверка оплаты |
| Membership | `handlers/admin/membership.py` | Динамические админы |
| Admin Panel | `handlers/admin/admin_panel.py, services_crud.py, stats.py` | /admin, CRUD, статистика |
| Keyboards | `keyboards/reply.py, inline.py` | Reply и Inline клавиатуры |
| Texts | `data/texts.py` | Разделение UA/RU |

### 2.3 База данных (ER)

```sql
users(user_id PK, username, full_name, custom_name, age, plan_date, service_id FK, source, first_seen, last_active, is_banned)
services(id PK, emoji, title, button_label UNIQUE, short_desc, terms, is_active, created_at)
tickets(id PK, user_id FK, admin_message_id UNIQUE, admin_chat_id, service_id, status[open/invoice_sent/paid/declined], created_at)
admins(user_id PK, added_at, added_by)
invoices(id PK, crypto_invoice_id UNIQUE, user_id FK, ticket_id FK, asset, amount, bot_invoice_url, mini_app_url, status[active/paid], payload, created_at)
messages_log(id PK, user_id, ticket_id, direction[user_to_admin/admin_to_user], text, created_at)
```
Индексы по `admin_message_id`, `user_id`, `crypto_invoice_id` для быстрого поиска тикетов.

---

## 3. Детальные флоу

### 3.1 User Flow (Українська)

```
 /start (с параметром source?)
   ↓
 WELCOME_TEXT_UA + ReplyKeyboard[Услуги из БД]
   ↓ (нажал кнопку услуги)
 SERVICE_CHOSEN_HEADER_UA + terms из БД + Inline[✅ Погоджуюсь]
   ↓
 agree:service_id → FSM Questionnaire
   1. ASK_NAME_UA → name
   2. ASK_AGE_UA → валидация 16-99
   3. ASK_PLAN_DATE_UA → plan_date
   ↓
 Создается тикет, отправка в админ-чат с кнопками [Подтвердить][Отклонить]
   ↓
 FINAL_USER_MESSAGE_UA
   ↓
 Любое новое сообщение → user_chat.py → форвард в админ-чат как reply к тикету + "Повідомлення передано"
   ↓
 Получает INVOICE_CREATED_USER_UA + кнопки [Оплатити через CryptoBot](url) [Перевірити оплату]
   ↓
 После оплаты → INVOICE_PAID_USER_UA
```

### 3.2 Admin Flow (Русский)

**Получение заявки:**
```
Админ-чат получает:
🔔 НОВАЯ ЗАЯВКА — 21.07.2026 17:30
👤 Обращение: ...
💎 Услуга: VIP
[✅ Подтвердить заявку] [❌ Отклонить]
```

**Вариант A — Ответить текстом:**
- Админ делает REPLY на сообщение заявки и пишет текст/фото/документ.
- `reply_handler.py` ловит `F.reply_to_message`, ищет `get_ticket_by_admin_msg(reply_to_id)`
- Отправляет юзеру от имени бота: `💬 Відповідь від адміністрації: ...`
- Логирует, подтверждает админу `✅ Отправлено пользователю`

**Вариант B — Подтвердить с ценой:**
1.  Нажатие `ticket:confirm:{admin_message_id}` → FSM `ConfirmPayment.waiting_price`
2.  Бот в админ-чате: `Введите договорную цену в формате: 100 USDT`
3.  Админ пишет `150 USDT` → `parse_price()` → `(150, "USDT")`
4.  Вызов `create_infinite_invoice(asset, amount, description, payload)`:
    ```python
    client = AioCryptoPay(token, network)
    invoice = await client.create_invoice(
        asset="USDT",
        amount=150,
        description="Оплата VIP...",
        payload="user_id:ticket_id:admin_msg_id",
        allow_anonymous=True,
        # expires_in не передаем → бесконечный
    )
    ```
5.  Сохранение в `invoices`, отправка юзеру, отправка админу, смена статуса тикета на `invoice_sent`.

**Вариант C — Отклонить:**
- Нажатие `ticket:decline` → FSM `waiting_decline_reason` → админ пишет причину → улетает юзеру `Вашу заявку відхилено`.

### 3.3 CryptoBot Payment Flow

- Инвойс бесконечный, потому что `expires_in` не указывается. В Crypto Pay API если не указать expires_in, счет живет пока не оплатят или не удалишь.
- Payload используется для связки: `user_id:ticket_id`
- Проверка: `get_invoices(invoice_ids=id)` → `status == "paid"`
- Поддерживаемые активы: BTC, TON, ETH, USDT, USDC, BUSD, TRX, SOL и др. Бот принимает любой, валидация на стороне CryptoBot.
- Тестовая сеть: используй @CryptoTestnetBot + `CRYPTO_BOT_IS_MAINNET=False` — можно тестировать без реальных денег.

---

## 4. Конфигурация

### .env

```
BOT_TOKEN=123456:AAH... - из @BotFather /newbot
ADMIN_CHAT_ID=-1001234567890 - ID группы админов (узнать через @userinfobot)
CRYPTO_BOT_TOKEN=12345:AAH... - из @CryptoBot /pay -> Create App
CRYPTO_BOT_IS_MAINNET=True - True для @CryptoBot, False для @CryptoTestnetBot
DB_PATH=bot.db - путь к SQLite
```

### Как получить ADMIN_CHAT_ID
1. Создай группу
2. Добавь в нее @userinfobot и бота
3. @userinfobot напишет `chat id: -100...` — это и есть ADMIN_CHAT_ID
4. Сделай бота админом группы (нужно для edit_message_reply_markup)

### Как получить CRYPTO_BOT_TOKEN
1. Открой @CryptoBot (или @CryptoTestnetBot)
2. /pay → Create App → введи название → получишь токен
3. Включи в настройках приложения Checks/Invoices если спросит

---

## 5. Админ-панель

Команда `/admin` доступна в админ-чате для всех (авто-регистрация) и в личке только для тех кто в таблице `admins`.

**Меню:**
```
[ 📊 Статистика ] [ 🛠 Услуги ]
[ 👥 Админы ]
```

**📊 Статистика:**
- Всего юзеров, сегодня, открытых диалогов, топ-услуга
- `/users` — список последних 20: `user_id | имя | возраст | service_id | source | @username`

**🛠 Услуги:**
- Список: `🟢 VIP Супровід` / `🔴 Выключена`
- Просмотр карточки: ID, кнопка, описание, условия, статус
- Действия: ✏️ Редактировать (пока меняет только условия), ❌ Удалить, 🔴/🟢 Вкл/Выкл
- ➕ Добавить: FSM 6 шагов: ID латиницей, эмодзи, название, текст кнопки, короткое описание, полные условия (HTML)

**👥 Админы:**
- Список всех с датой добавления. Динамически обновляется при входе/выходе из админ-чата.

---

## 6. Установка и деплой

### Локально

```bash
pip install -r requirements.txt
cp .env.example .env
# заполни .env
python -m app.bot
```

### Docker

```bash
docker-compose up -d --build
docker-compose logs -f
```

`docker-compose.yml`:
- `restart: unless-stopped`
- volume `./bot.db:/app/bot.db` для сохранения БД
- `env_file: .env`

### Systemd (на VPS без Docker)

Создай `/etc/systemd/system/servicebot.service`:

```
[Unit]
Description=Telegram Service Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/service-bot-v2
ExecStart=/home/ubuntu/service-bot-v2/venv/bin/python -m app.bot
Restart=always
EnvironmentFile=/home/ubuntu/service-bot-v2/.env

[Install]
WantedBy=multi-user.target
```

`systemctl daemon-reload && systemctl enable --now servicebot`

---

## 7. Безопасность

- Токены только в `.env`, `.env` в `.gitignore`
- Админ-чат должен быть приватным, invite-link не светить
- Ответы юзеру всегда от имени бота, ID админов не палятся
- Антифлуд можно добавить middleware (1.5 сек для юзеров)
- SQLite WAL режим, бэкап `bot.db` ежедневно
- Логи без персональных данных, `messages_log` только для аудита
- Инвойсы CryptoBot — одноразовые, payload не содержит секретов

---

## 8. Источник (Канал)

Поддерживается deep-link:

- Создай ссылку `https://t.me/your_bot?start=channel_top`
- Размести в канале @channel_top
- Когда юзер переходит, `parse_source()` сохраняет `channel_top` в `users.source`
- Админ видит `Источник: channel_top` в заявке и в приветствии
- Можно делать разные ссылки для разных каналов и считать эффективность.

Если нужен именно авто-детект вступления в канал — сделай бота админом канала и включи `chat_member` events (уже есть заготовка в `membership.py`).

---

## 9. FAQ и Troubleshooting

**Q: Админ не видит кнопку Подтвердить?**
A: Бот должен быть админом в админ-чате с правом `Edit messages`.

**Q: CryptoBot пишет ошибку токена?**
A: Проверь `CRYPTO_BOT_TOKEN`, сеть (MAINNET vs TESTNET), баланс приложения (пополни в @CryptoBot).

**Q: Юзер не получает ответ админа?**
A: Юзер заблокировал бота. Бот напишет админу `Не удалось отправить`.

**Q: Как добавить новую услугу без перезапуска?**
A: В админ-чате `/admin` → Услуги → Добавить. Сразу появится в Reply-клавиатуре.

**Q: Как выдать права новому админу?**
A: Просто добавь его в админ-чат. `membership.py` авто-выдаст.

---

## 10. Дальнейшее развитие

- Webhook вместо polling + FastAPI для CryptoBot webhook уведомлений об оплате (мгновенное подтверждение без кнопки Проверить)
- RedisStorage для FSM чтобы не терять анкеты при рестарте
- Рассылка по пользователям из админ-панели
- Экспорт статистики в Excel
- Мультиязычность для админов (RU/UA)
- Интеграция с TRC20 / TON напрямую без CryptoBot

---

## 11. Файлы проекта

```
service-bot-v2/
├── app/bot.py
├── app/config.py
├── app/database/
├── app/data/texts.py
├── app/handlers/
├── app/keyboards/
├── app/services/cryptopay.py
├── app/states/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
└── DOCUMENTATION.md (этот файл)
```

**Автор:** Senior Python/Aiogram Architect  
**Лицензия:** Private
