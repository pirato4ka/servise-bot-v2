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
    title TEXT NOT NULL,
    button_label TEXT NOT NULL UNIQUE,
    short_desc TEXT,
    terms TEXT NOT NULL,
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tickets_admin_msg ON tickets(admin_message_id);
CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_user ON invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_crypto ON invoices(crypto_invoice_id);
"""


async def init_db():
    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()

        # Миграция: добавляем колонку lang если нет
        async with db.execute("PRAGMA table_info(users)") as cur:
            columns = [row[1] for row in await cur.fetchall()]
        if "lang" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT NULL")
            await db.commit()
        if "is_banned" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
            await db.commit()

       


async def get_db():
    db = await aiosqlite.connect(settings.DB_PATH)
    db.row_factory = aiosqlite.Row
    return db
