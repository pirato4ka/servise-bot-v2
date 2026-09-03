import logging

import aiosqlite

from app.config import settings

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    custom_name TEXT,
    age INTEGER,
    plan_date TEXT,
    recipient TEXT,
    service_id TEXT,
    source TEXT DEFAULT 'direct',
    lang TEXT DEFAULT NULL,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_banned INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY,
    emoji TEXT,
    title_ua TEXT NOT NULL,
    title_ru TEXT NOT NULL,
    button_label_ua TEXT NOT NULL UNIQUE,
    button_label_ru TEXT NOT NULL UNIQUE,
    short_desc_ua TEXT,
    short_desc_ru TEXT,
    terms_ua TEXT NOT NULL,
    terms_ru TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by INTEGER
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    admin_message_id INTEGER NOT NULL,
    admin_chat_id INTEGER NOT NULL,
    service_id TEXT,
    status TEXT DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS messages_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    ticket_id INTEGER,
    direction TEXT,
    text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crypto_invoice_id INTEGER,
    user_id INTEGER NOT NULL,
    ticket_id INTEGER,
    asset TEXT,
    amount TEXT,
    bot_invoice_url TEXT,
    mini_app_url TEXT,
    status TEXT DEFAULT 'active',
    payload TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    interval_hours REAL NOT NULL,
    text TEXT NOT NULL,
    photo_file_id TEXT,
    is_active INTEGER DEFAULT 1,
    last_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- FSM-состояния (мастера услуг, анкета, рассылки, подтверждение оплаты).
-- Хранятся в БД, чтобы рестарт бота не обнулял незавершённые диалоги
-- (раньше aiogram держал их в памяти и терял при перезапуске).
CREATE TABLE IF NOT EXISTS fsm_states (
    bot_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    thread_id INTEGER NOT NULL DEFAULT 0,
    business_connection_id TEXT NOT NULL DEFAULT '',
    destiny TEXT NOT NULL DEFAULT 'default',
    state TEXT,
    data TEXT NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bot_id, chat_id, user_id, thread_id,
                 business_connection_id, destiny)
);

-- Связь «сообщение в админ-чате -> заявка».
-- Позволяет находить заявку по reply даже на 3-5 уровне вложенности
-- и не терять диалог после перезапуска бота.
CREATE TABLE IF NOT EXISTS admin_messages (
    admin_message_id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    parent_message_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tickets_admin_msg ON tickets(admin_message_id);
CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_user ON invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_crypto ON invoices(crypto_invoice_id);
CREATE INDEX IF NOT EXISTS idx_admin_messages_ticket ON admin_messages(ticket_id);
CREATE INDEX IF NOT EXISTS idx_broadcasts_active ON broadcasts(is_active);
"""

# Миграции для баз, созданных старыми версиями: (таблица, колонка, DDL)
COLUMN_MIGRATIONS = (
    ("users", "lang", "ALTER TABLE users ADD COLUMN lang TEXT DEFAULT NULL"),
    ("users", "is_banned", "ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0"),
    ("users", "plan_date", "ALTER TABLE users ADD COLUMN plan_date TEXT"),
    ("users", "recipient", "ALTER TABLE users ADD COLUMN recipient TEXT"),
    ("broadcasts", "last_sent_at", "ALTER TABLE broadcasts ADD COLUMN last_sent_at TIMESTAMP"),
)


async def _apply_pragmas(db: aiosqlite.Connection) -> None:
    """WAL + busy_timeout: иначе при параллельных запросах ловим 'database is locked'."""
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA foreign_keys=ON")


SERVICES_BILINGUAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY,
    emoji TEXT,
    title_ua TEXT NOT NULL,
    title_ru TEXT NOT NULL,
    button_label_ua TEXT NOT NULL UNIQUE,
    button_label_ru TEXT NOT NULL UNIQUE,
    short_desc_ua TEXT,
    short_desc_ru TEXT,
    terms_ua TEXT NOT NULL,
    terms_ru TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def _migrate_services_to_bilingual(db: aiosqlite.Connection) -> None:
    """
    Старая таблица услуг была одноязычной (title, button_label, short_desc, terms).
    Переливаем её в двуязычную: старые значения попадают сразу в UA и RU,
    чтобы ничего не сломалось, а админ потом поправит перевод.
    """
    async with db.execute("PRAGMA table_info(services)") as cur:
        columns = {row[1] for row in await cur.fetchall()}

    if not columns or "title_ua" in columns:
        return  # уже новая схема

    await db.execute("ALTER TABLE services RENAME TO services_old")
    await db.executescript(SERVICES_BILINGUAL_SCHEMA)
    await db.execute("""
        INSERT INTO services (id, emoji, title_ua, title_ru, button_label_ua, button_label_ru,
                              short_desc_ua, short_desc_ru, terms_ua, terms_ru, is_active, created_at)
        SELECT id, emoji, title, title, button_label, button_label, short_desc, short_desc,
               terms, terms, is_active, created_at
        FROM services_old
    """)
    await db.execute("DROP TABLE services_old")
    await db.commit()
    logging.getLogger(__name__).info(
        "Миграция: услуги переведены на двуязычную схему (старые значения продублированы в UA и RU)"
    )


async def _add_missing_columns(db: aiosqlite.Connection) -> None:
    for table, column, ddl in COLUMN_MIGRATIONS:
        async with db.execute(f"PRAGMA table_info({table})") as cur:
            rows = await cur.fetchall()
        if not rows:  # таблицы ещё нет — её создаст CREATE_TABLES
            continue
        existing = {row[1] for row in rows}
        if column not in existing:
            await db.execute(ddl)
    await db.commit()


async def init_db():
    async with aiosqlite.connect(settings.DB_PATH, timeout=15.0) as db:
        await _apply_pragmas(db)
        await db.executescript(CREATE_TABLES)
        await db.commit()
        await _migrate_services_to_bilingual(db)
        await _add_missing_columns(db)


async def get_db():
    db = await aiosqlite.connect(settings.DB_PATH, timeout=15.0)
    db.row_factory = aiosqlite.Row
    await _apply_pragmas(db)
    return db
