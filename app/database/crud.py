import aiosqlite
from .db import get_db

# USERS
async def upsert_user(user_id: int, username: str, full_name: str, source: str = "direct"):
    db = await get_db()
    await db.execute("""
        INSERT INTO users (user_id, username, full_name, source, last_active)
        VALUES (?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name, last_active=CURRENT_TIMESTAMP, source=COALESCE(users.source, excluded.source)
    """, (user_id, username, full_name, source))
    await db.commit()
    await db.close()

async def update_user_questionnaire(user_id: int, custom_name: str, age: int, plan_date: str, service_id: str):
    db = await get_db()
    await db.execute("UPDATE users SET custom_name=?, age=?, plan_date=?, service_id=? WHERE user_id=?", (custom_name, age, plan_date, service_id, user_id))
    await db.commit()
    await db.close()


async def get_users_count():
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM users") as cur:
        c = (await cur.fetchone())[0]
    await db.close()
    return c

async def get_service_by_id(sid: str):
    db = await get_db()
    async with db.execute("SELECT * FROM services WHERE id=?", (sid,)) as cur:
        row = await cur.fetchone()
    await db.close()
    return row

async def get_service_by_button(label: str):
    db = await get_db()
    async with db.execute("SELECT * FROM services WHERE button_label=?", (label,)) as cur:
        row = await cur.fetchone()
    await db.close()
    return row

async def create_service(data: dict):
    db = await get_db()
    await db.execute("INSERT INTO services (id, emoji, title, button_label, short_desc, terms) VALUES (?,?,?,?,?,?)",
                     (data['id'], data['emoji'], data['title'], data['button_label'], data['short_desc'], data['terms']))
    await db.commit()
    await db.close()

async def update_service(sid: str, data: dict):
    db = await get_db()
    await db.execute("UPDATE services SET emoji=?, title=?, button_label=?, short_desc=?, terms=? WHERE id=?",
                     (data['emoji'], data['title'], data['button_label'], data['short_desc'], data['terms'], sid))
    await db.commit()
    await db.close()

async def delete_service(sid: str):
    db = await get_db()
    await db.execute("DELETE FROM services WHERE id=?", (sid,))
    await db.commit()
    await db.close()

async def toggle_service(sid: str):
    db = await get_db()
    await db.execute("UPDATE services SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?", (sid,))
    await db.commit()
    await db.close()

# TICKETS
async def create_ticket(user_id: int, admin_message_id: int, admin_chat_id: int, service_id: str):
    db = await get_db()
    cur = await db.execute("INSERT INTO tickets (user_id, admin_message_id, admin_chat_id, service_id) VALUES (?,?,?,?)",
                     (user_id, admin_message_id, admin_chat_id, service_id))
    ticket_id = cur.lastrowid
    await db.commit()
    await db.close()
    return ticket_id

async def get_ticket_by_admin_msg(admin_message_id: int):
    db = await get_db()
    async with db.execute("SELECT * FROM tickets WHERE admin_message_id=?", (admin_message_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    return row

async def get_ticket_by_id(tid: int):
    db = await get_db()
    async with db.execute("SELECT * FROM tickets WHERE id=?", (tid,)) as cur:
        row = await cur.fetchone()
    await db.close()
    return row

async def get_open_ticket_by_user(user_id: int):
    db = await get_db()
    async with db.execute("SELECT * FROM tickets WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1", (user_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    return row

async def get_last_ticket_by_user(user_id: int):
    db = await get_db()
    async with db.execute("SELECT * FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    return row

# ADMINS
async def add_admin(user_id: int, added_by: int = None):
    db = await get_db()
    await db.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?,?)", (user_id, added_by))
    await db.commit()
    await db.close()

async def remove_admin(user_id: int):
    db = await get_db()
    await db.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    await db.commit()
    await db.close()

async def is_admin(user_id: int) -> bool:
    db = await get_db()
    async with db.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)) as cur:
        r = await cur.fetchone()
    await db.close()
    return r is not None

async def log_message(user_id: int, ticket_id: int, direction: str, text: str):
    db = await get_db()
    await db.execute("INSERT INTO messages_log (user_id, ticket_id, direction, text) VALUES (?,?,?,?)", (user_id, ticket_id, direction, text))
    await db.commit()
    await db.close()

# INVOICES
async def create_invoice_record(crypto_invoice_id: int, user_id: int, ticket_id: int, asset: str, amount: str, bot_url: str, mini_url: str, payload: str):
    db = await get_db()
    await db.execute("INSERT INTO invoices (crypto_invoice_id, user_id, ticket_id, asset, amount, bot_invoice_url, mini_app_url, payload) VALUES (?,?,?,?,?,?,?,?)",
                     (crypto_invoice_id, user_id, ticket_id, asset, amount, bot_url, mini_url, payload))
    await db.commit()
    await db.close()

async def get_invoice_by_crypto_id(crypto_id: int):
    db = await get_db()
    async with db.execute("SELECT * FROM invoices WHERE crypto_invoice_id=?", (crypto_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    return row

async def get_invoices_by_user(user_id: int):
    db = await get_db()
    async with db.execute("SELECT * FROM invoices WHERE user_id=? ORDER BY id DESC", (user_id,)) as cur:
        rows = await cur.fetchall()
    await db.close()
    return rows

async def update_invoice_status(crypto_id: int, status: str):
    db = await get_db()
    await db.execute("UPDATE invoices SET status=? WHERE crypto_invoice_id=?", (status, crypto_id))
    await db.commit()
    await db.close()

# LANG
async def get_user_lang(user_id: int) -> str:
    db = await get_db()
    async with db.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    return row["lang"] if row and row["lang"] else "ua"

async def set_user_lang(user_id: int, lang: str):
    db = await get_db()
    await db.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
    await db.commit()
    await db.close()

# BAN
async def ban_user(user_id: int):
    db = await get_db()
    await db.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
    await db.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, 1)", (user_id,))
    await db.commit()
    await db.close()

async def unban_user(user_id: int):
    db = await get_db()
    await db.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
    await db.commit()
    await db.close()

async def is_banned(user_id: int) -> bool:
    db = await get_db()
    async with db.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    return bool(row and row["is_banned"])

async def get_user_by_username(username: str):
    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE username=?", (username.lstrip("@"),)) as cur:
        row = await cur.fetchone()
    await db.close()
    return row

# app/database/crud.py — все функции возвращающие списки строк

async def get_all_users(limit=20, offset=0):
    db = await get_db()
    async with db.execute(
        "SELECT * FROM users ORDER BY last_active DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ) as cur:
        rows = await cur.fetchall()
    await db.close()
    return [dict(row) for row in rows]  # ← добавь везде


async def get_services(active_only=True):
    db = await get_db()
    query = (
        "SELECT * FROM services WHERE is_active = 1 ORDER BY created_at"
        if active_only else
        "SELECT * FROM services ORDER BY created_at"
    )
    async with db.execute(query) as cur:
        rows = await cur.fetchall()
    await db.close()
    return [dict(row) for row in rows]  # ← добавь везде


async def get_admins():
    db = await get_db()
    async with db.execute("SELECT * FROM admins") as cur:
        rows = await cur.fetchall()
    await db.close()
    return [dict(row) for row in rows]  # ← добавь везде