from typing import Optional

from .db import get_db

# USERS
async def upsert_user(user_id: int, username: str, full_name: str, source: str = "direct"):
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name, source, last_active)
            VALUES (?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name, last_active=CURRENT_TIMESTAMP, source=COALESCE(users.source, excluded.source)
        """, (user_id, username, full_name, source))
        await db.commit()
    finally:
        await db.close()


async def update_user_questionnaire(user_id: int, custom_name: str, age: int, recipient: str, service_id: str):
    """Третий шаг анкеты — «кому требуется услуга» (Мне / Родному / Другу)."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET custom_name=?, age=?, recipient=?, service_id=?, plan_date=NULL WHERE user_id=?",
            (custom_name, age, recipient, service_id, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_user(user_id: int):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        return row
    finally:
        await db.close()


async def get_users_count():
    db = await get_db()
    try:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            c = (await cur.fetchone())[0]
        return c
    finally:
        await db.close()


LANGS = ("ua", "ru")
SERVICE_LOCALIZED_FIELDS = ("title", "button_label", "short_desc", "terms")


def localize_service(service, lang: str = "ua") -> dict | None:
    """
    Разворачивает запись услуги под язык пользователя:
    {title_ua, title_ru} + lang='ua' -> {'title': ..., 'button_label': ...}
    Если перевод для языка пустой — берём второй язык.
    """
    if not service:
        return None

    row = dict(service)
    lang = lang if lang in LANGS else "ua"
    other = "ru" if lang == "ua" else "ua"

    for field in SERVICE_LOCALIZED_FIELDS:
        value = row.get(f"{field}_{lang}")
        if value in (None, ""):
            value = row.get(f"{field}_{other}")
        row[field] = value
    return row


async def get_service_by_id(sid: str):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM services WHERE id=?", (sid,)) as cur:
            row = await cur.fetchone()
        return row
    finally:
        await db.close()


async def get_service_by_button(label: str):
    """Кнопка может быть на любом языке — ищем по обеим колонкам."""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT * FROM services WHERE button_label_ua=? OR button_label_ru=?", (label, label)
        ) as cur:
            row = await cur.fetchone()
        return row
    finally:
        await db.close()


async def is_button_label_taken(label: str, exclude_id: str = None) -> bool:
    db = await get_db()
    try:
        if exclude_id:
            async with db.execute(
                "SELECT 1 FROM services WHERE (button_label_ua=? OR button_label_ru=?) AND id<>?",
                (label, label, exclude_id),
            ) as cur:
                row = await cur.fetchone()
        else:
            async with db.execute(
                "SELECT 1 FROM services WHERE button_label_ua=? OR button_label_ru=?", (label, label)
            ) as cur:
                row = await cur.fetchone()
        return row is not None
    finally:
        await db.close()


def _service_fields(data: dict) -> tuple:
    """Достаёт двуязычные поля из словаря мастера добавления/редактирования."""
    return (
        data.get("emoji", ""),
        data.get("title_ua", ""), data.get("title_ru", ""),
        data.get("button_label_ua", ""), data.get("button_label_ru", ""),
        data.get("short_desc_ua", ""), data.get("short_desc_ru", ""),
        data.get("terms_ua", ""), data.get("terms_ru", ""),
    )


async def create_service(data: dict):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO services (id, emoji, title_ua, title_ru, button_label_ua, button_label_ru, "
            "short_desc_ua, short_desc_ru, terms_ua, terms_ru) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (data["id"], *_service_fields(data)),
        )
        await db.commit()
    finally:
        await db.close()


async def update_service(sid: str, data: dict):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE services SET emoji=?, title_ua=?, title_ru=?, button_label_ua=?, button_label_ru=?, "
            "short_desc_ua=?, short_desc_ru=?, terms_ua=?, terms_ru=? WHERE id=?",
            (*_service_fields(data), sid),
        )
        await db.commit()
    finally:
        await db.close()


EDITABLE_FIELDS = ("emoji", "title", "button_label", "short_desc", "terms")


async def update_service_field(sid: str, field: str, value: str):
    """Правка одного поля: 'emoji' или '<поле>_<язык>' (например terms_ua)."""
    if field not in EDITABLE_FIELDS and not any(field == f"{f}_{lang}" for f in SERVICE_LOCALIZED_FIELDS for lang in LANGS):
        raise ValueError(f"Недопустимое поле услуги: {field}")
    db = await get_db()
    try:
        await db.execute(f"UPDATE services SET {field}=? WHERE id=?", (value, sid))
        await db.commit()
    finally:
        await db.close()


async def copy_service_language(sid: str, source: str = "ua"):
    """Копирует UA-тексты в RU (или наоборот) — чтобы не перепечатывать вручную."""
    target = "ru" if source == "ua" else "ua"
    fields = ", ".join(f"{f}_{target}={f}_{source}" for f in SERVICE_LOCALIZED_FIELDS)
    db = await get_db()
    try:
        await db.execute(f"UPDATE services SET {fields} WHERE id=?", (sid,))
        await db.commit()
    finally:
        await db.close()


async def delete_service(sid: str):
    db = await get_db()
    try:
        await db.execute("DELETE FROM services WHERE id=?", (sid,))
        await db.commit()
    finally:
        await db.close()


async def toggle_service(sid: str):
    db = await get_db()
    try:
        await db.execute("UPDATE services SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?", (sid,))
        await db.commit()
    finally:
        await db.close()


# TICKETS
async def create_ticket(user_id: int, admin_message_id: int, admin_chat_id: int, service_id: str):
    db = await get_db()
    try:
        cur = await db.execute("INSERT INTO tickets (user_id, admin_message_id, admin_chat_id, service_id) VALUES (?,?,?,?)",
                               (user_id, admin_message_id, admin_chat_id, service_id))
        ticket_id = cur.lastrowid
        await db.commit()
    finally:
        await db.close()
    # Корневое сообщение заявки — якорь для reply-цепочки
    await link_admin_message(admin_message_id, ticket_id, None)
    return ticket_id


async def get_ticket_by_admin_msg(admin_message_id: int):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM tickets WHERE admin_message_id=?", (admin_message_id,)) as cur:
            row = await cur.fetchone()
        return row
    finally:
        await db.close()


async def get_ticket_by_id(tid: int):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM tickets WHERE id=?", (tid,)) as cur:
            row = await cur.fetchone()
        return row
    finally:
        await db.close()


async def get_open_ticket_by_user(user_id: int):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM tickets WHERE user_id=? AND status='open' ORDER BY id DESC LIMIT 1", (user_id,)) as cur:
            row = await cur.fetchone()
        return row
    finally:
        await db.close()


async def get_last_ticket_by_user(user_id: int):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)) as cur:
            row = await cur.fetchone()
        return row
    finally:
        await db.close()


async def set_ticket_status(ticket_id: int, status: str):
    db = await get_db()
    try:
        await db.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))
        await db.commit()
    finally:
        await db.close()


# ADMIN MESSAGES (карта «сообщение в админ-чате -> заявка»)
async def link_admin_message(admin_message_id: Optional[int], ticket_id: int, parent_message_id: Optional[int]):
    """Запоминаем, к какой заявке относится сообщение в админ-чате."""
    if not admin_message_id:
        return
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO admin_messages (admin_message_id, ticket_id, parent_message_id) VALUES (?,?,?) "
            "ON CONFLICT(admin_message_id) DO UPDATE SET ticket_id=excluded.ticket_id, parent_message_id=excluded.parent_message_id",
            (admin_message_id, ticket_id, parent_message_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_admin_message(admin_message_id: int):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM admin_messages WHERE admin_message_id=?", (admin_message_id,)) as cur:
            row = await cur.fetchone()
        return row
    finally:
        await db.close()


async def resolve_ticket_by_admin_message(admin_message_id: int, max_depth: int = 15) -> Optional[dict]:
    """
    Находим заявку по сообщению в админ-чате.
    Работает для reply любой вложенности: идём вверх по parent_message_id.
    """
    seen = set()
    current = admin_message_id
    for _ in range(max_depth):
        if current is None or current in seen:
            return None
        seen.add(current)

        ticket = await get_ticket_by_admin_msg(current)
        if ticket:
            return ticket

        link = await get_admin_message(current)
        if not link:
            return None
        current = link["parent_message_id"]
    return None


# ADMINS
async def add_admin(user_id: int, added_by: int = None):
    db = await get_db()
    try:
        await db.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?,?)", (user_id, added_by))
        await db.commit()
    finally:
        await db.close()


async def remove_admin(user_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
        await db.commit()
    finally:
        await db.close()


async def is_admin(user_id: int) -> bool:
    db = await get_db()
    try:
        async with db.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)) as cur:
            r = await cur.fetchone()
        return r is not None
    finally:
        await db.close()


async def log_message(user_id: int, ticket_id: int, direction: str, text: str):
    db = await get_db()
    try:
        await db.execute("INSERT INTO messages_log (user_id, ticket_id, direction, text) VALUES (?,?,?,?)",
                         (user_id, ticket_id, direction, text))
        await db.commit()
    finally:
        await db.close()


# INVOICES
async def create_invoice_record(crypto_invoice_id: int, user_id: int, ticket_id: int, asset: str, amount: str,
                                bot_url: str, mini_url: str, payload: str):
    db = await get_db()
    try:
        await db.execute("INSERT INTO invoices (crypto_invoice_id, user_id, ticket_id, asset, amount, bot_invoice_url, mini_app_url, payload) VALUES (?,?,?,?,?,?,?,?)",
                         (crypto_invoice_id, user_id, ticket_id, asset, amount, bot_url, mini_url, payload))
        await db.commit()
    finally:
        await db.close()


async def get_invoice_by_crypto_id(crypto_id: int):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM invoices WHERE crypto_invoice_id=?", (crypto_id,)) as cur:
            row = await cur.fetchone()
        return row
    finally:
        await db.close()


async def get_invoices_by_user(user_id: int):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM invoices WHERE user_id=? ORDER BY id DESC", (user_id,)) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def update_invoice_status(crypto_id: int, status: str):
    db = await get_db()
    try:
        await db.execute("UPDATE invoices SET status=? WHERE crypto_invoice_id=?", (status, crypto_id))
        await db.commit()
    finally:
        await db.close()


async def get_pending_invoices(limit: int = 50):
    """Активные счета для фоновой проверки оплаты."""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT * FROM invoices WHERE status IN ('active','pending') AND crypto_invoice_id IS NOT NULL "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def mark_invoice_paid(crypto_id: int) -> Optional[dict]:
    """Отмечаем счёт оплаченным и закрываем заявку. Возвращает запись счёта (или None)."""
    record = await get_invoice_by_crypto_id(crypto_id)
    if not record:
        return None
    if record["status"] == "paid":
        return None
    await update_invoice_status(crypto_id, "paid")
    if record["ticket_id"]:
        await set_ticket_status(record["ticket_id"], "paid")
    return dict(record)


# LANG
async def get_user_lang(user_id: int) -> str:
    db = await get_db()
    try:
        async with db.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        return row["lang"] if row and row["lang"] else "ua"
    finally:
        await db.close()


async def set_user_lang(user_id: int, lang: str):
    db = await get_db()
    try:
        await db.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
        await db.commit()
    finally:
        await db.close()


# BAN
async def ban_user(user_id: int):
    db = await get_db()
    try:
        await db.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
        await db.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, 1)", (user_id,))
        await db.commit()
    finally:
        await db.close()


async def unban_user(user_id: int):
    db = await get_db()
    try:
        await db.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
        await db.commit()
    finally:
        await db.close()


async def is_banned(user_id: int) -> bool:
    db = await get_db()
    try:
        async with db.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        return bool(row and row["is_banned"])
    finally:
        await db.close()


async def get_user_by_username(username: str):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM users WHERE username=?", (username.lstrip("@"),)) as cur:
            row = await cur.fetchone()
        return row
    finally:
        await db.close()


async def get_all_users(limit: int = 20, offset: int = 0):
    db = await get_db()
    try:
        async with db.execute(
            "SELECT * FROM users ORDER BY last_active DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_broadcast_targets(limit: int = 10000):
    """Получатели рассылки: без забаненных и без админов."""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT u.* FROM users u "
            "LEFT JOIN admins a ON a.user_id = u.user_id "
            "WHERE a.user_id IS NULL AND COALESCE(u.is_banned, 0) = 0 "
            "LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_services(active_only: bool = True):
    db = await get_db()
    try:
        query = (
            "SELECT * FROM services WHERE is_active = 1 ORDER BY created_at"
            if active_only else
            "SELECT * FROM services ORDER BY created_at"
        )
        async with db.execute(query) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_admins():
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM admins") as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


# BROADCASTS (перенесено из SQL внутри хендлеров)
async def create_broadcast(admin_id: int, interval_hours: float, text: str, photo_file_id: Optional[str]) -> Optional[int]:
    db = await get_db()
    try:
        cur = await db.execute(
            "INSERT INTO broadcasts (admin_id, interval_hours, text, photo_file_id, is_active) VALUES (?,?,?,?,1)",
            (admin_id, interval_hours, text, photo_file_id),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def get_broadcast(broadcast_id: int):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM broadcasts WHERE id=?", (broadcast_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_active_broadcasts():
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM broadcasts WHERE is_active = 1 ORDER BY id") as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def touch_broadcast(broadcast_id: int):
    db = await get_db()
    try:
        await db.execute("UPDATE broadcasts SET last_sent_at=CURRENT_TIMESTAMP WHERE id=?", (broadcast_id,))
        await db.commit()
    finally:
        await db.close()


async def deactivate_broadcast(broadcast_id: int):
    db = await get_db()
    try:
        await db.execute("UPDATE broadcasts SET is_active = 0 WHERE id=?", (broadcast_id,))
        await db.commit()
    finally:
        await db.close()


async def get_recent_broadcasts(limit: int = 10):
    db = await get_db()
    try:
        async with db.execute("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ?", (limit,)) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# STATS
async def get_stats():
    db = await get_db()
    try:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE date(first_seen)=date('now')") as cur:
            today = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM tickets WHERE status='open'") as cur:
            open_t = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM tickets WHERE status='paid'") as cur:
            paid_t = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT service_id, COUNT(*) as c FROM users WHERE service_id IS NOT NULL "
            "GROUP BY service_id ORDER BY c DESC LIMIT 1"
        ) as cur:
            top = await cur.fetchone()
        return {"total": total, "today": today, "open_t": open_t, "paid_t": paid_t,
                "top_service": top["service_id"] if top else None, "top_count": top["c"] if top else 0}
    finally:
        await db.close()
