# Telegram Service Bot — Final v3 (CryptoBot + Reply-Bridge + Dynamic Admins)

Премиум бот для продажи услуг с акцентом на конфиденциальность. 

**Юзеру — украинский, админу — русский.**

### Функционал финала
1.  **Reply-Bridge:** Админ отвечает REPLY на заявку в админ-чате -> сообщение улетает юзеру от имени бота.
2.  **Продолжение диалога:** Любое сообщение юзера после анкеты форвардится в тред заявки.
3.  **Источник:** Поддержка deep-link `t.me/bot?start=channel_xxx` — пишется в заявке как "Источник".
4.  **Динамические админы:** Любой добавленный в админ-чат получает права автоматически. Отслеживается через `new_chat_members`, `left_chat_member`, `ChatMemberUpdated`.
5.  **Админ-панель `/admin`:** 
    - Статистика `/stats`, `/users`
    - CRUD услуг (➕ Добавить, ✏️ Редактировать, ❌ Удалить, 🔴/🟢 Вкл/Выкл)
    - Список админов
6.  **Оплата CryptoBot:** После заявки у админа кнопка `✅ Подтвердить`. При нажатии бот просит ввести договорную цену `100 USDT` -> создает **БЕСКОНЕЧНЫЙ инвойс** (без `expires_in`) и отправляет юзеру с кнопкой оплаты и проверки.

### Техстек
- Python 3.11 + aiogram 3.7
- SQLite + aiosqlite (таблицы: users, services, tickets, admins, invoices, messages_log)
- aiocryptopay для @CryptoBot

### Быстрый запуск (локально)

1. Клонируй папку, установи зависимости:
```bash
pip install -r requirements.txt
```

2. Создай `.env` из примера:
```bash
cp .env.example .env
nano .env
```
Содержимое `.env`:
```
BOT_TOKEN=123456:AAH...
ADMIN_CHAT_ID=-1001234567890
CRYPTO_BOT_TOKEN=12345:AAH... из @CryptoBot /pay
CRYPTO_BOT_IS_MAINNET=True
DB_PATH=bot.db
```

3. Запуск:
```bash
python -m app.bot
```

### Как получить токены

**BOT_TOKEN:**
- @BotFather -> /newbot -> копируешь токен

**ADMIN_CHAT_ID:**
- Создай группу, добавь туда бота и @userinfobot
- @userinfobot покажет ID группы (например -100...). Это ADMIN_CHAT_ID
- Сделай группу приватной, добавь туда всех админов

**CRYPTO_BOT_TOKEN:**
- Иди в @CryptoBot (прод) или @CryptoTestnetBot (тест, без реальных денег)
- /pay -> Create App -> вводишь название -> получаешь токен
- Для теста поставь CRYPTO_BOT_IS_MAINNET=False

### Запуск через Docker

```bash
docker-compose up -d --build
docker-compose logs -f
```

### Структура
```
app/
├── bot.py — точка входа
├── config.py
├── database/
│   ├── db.py — создание таблиц + сид услуг
│   └── crud.py
├── data/
│   └── texts.py — UA для юзера, RU для админа
├── keyboards/
│   ├── reply.py — услуги из БД (ReplyKeyboard под полем ввода)
│   └── inline.py — Подтвердить/Отклонить, инвойсы, админ-панель
├── handlers/
│   ├── start.py — /start + source tracking
│   ├── services.py — выбор услуги
│   ├── questionnaire.py — анкета + создает тикет + кнопки админу
│   ├── user_chat.py — свободные сообщения юзера -> в тред админ-чата
│   └── admin/
│       ├── reply_handler.py — Reply админа -> юзеру от имени бота
│       ├── confirm_payment.py — Подтвердить/Отклонить + ввод цены + бесконечный счет CryptoBot
│       ├── payment_check.py — Проверка оплаты
│       ├── admin_panel.py — /admin
│       ├── services_crud.py — добавление услуг через FSM
│       ├── stats.py — /stats /users
│       └── membership.py — динамические админы
├── services/
│   └── cryptopay.py — создание бесконечных инвойсов
└── states/
    ├── questionnaire.py
    └── admin_states.py — AddService, ConfirmPayment
```

### Флоу оплаты (договорная цена)

1. Юзер: выбирает услугу -> соглашается -> заполняет анкету (как зовут, возраст, когда планирует)
2. Админ-чат: приходит заявка с кнопками [Подтвердить] [Отклонить]
3. Админ: Нажимает Подтвердить -> бот просит "Введите цену: 100 USDT"
4. Админ: пишет цену -> бот через CryptoBot API создает инвойс без срока годности
5. Юзер: получает "Вашу заявку підтверджено! Договірна ціна: 100 USDT [Оплатити]" -> оплачивает в @CryptoBot
6. Юзер жмет "Перевірити оплату" -> бот дергает `get_invoices`
7. Оплата подтверждена -> админ уведомляется

### Важно
- Все ответы юзеру — от имени бота (анонимность админов сохранена)
- Все админские тексты — на русском, пользовательские — на украинском
- База bot.db хранится локально, не коммить .env
- Для продакшена на сервере используй `systemd` или `docker-compose restart: unless-stopped`

Готово к деплою.
"# servise-bot-v2" 
"# servise-bot-v2" 
