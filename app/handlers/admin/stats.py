from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from app.config import settings
from app.database import crud
from app.database.db import get_db
from app.data.texts import ADMIN_STATS_TEXT_RU, ADMIN_NO_USERS_RU, ADMIN_USERS_HEADER_RU, ADMIN_REQ_NO_RIGHTS_RU

router = Router()

async def get_stats_text():
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM users") as cur:
        total = (await cur.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM users WHERE date(first_seen)=date('now')") as cur:
        today = (await cur.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM tickets WHERE status='open'") as cur:
        open_t = (await cur.fetchone())[0]
    async with db.execute("SELECT service_id, COUNT(*) as c FROM users WHERE service_id IS NOT NULL GROUP BY service_id ORDER BY c DESC LIMIT 1") as cur:
        top = await cur.fetchone()
    await db.close()

    top_text = f"{top['service_id']} ({top['c']})" if top else "нет"
    
    return ADMIN_STATS_TEXT_RU.format(total=total, today=today, open_t=open_t, top_text=top_text)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.chat.id != settings.ADMIN_CHAT_ID and not await crud.is_admin(message.from_user.id):
        return
    text = await get_stats_text()
    await message.answer(text)

@router.message(Command("users"))
async def cmd_users(message: Message):
    if message.chat.id != settings.ADMIN_CHAT_ID and not await crud.is_admin(message.from_user.id):
        await message.answer(ADMIN_REQ_NO_RIGHTS_RU)
        return
    users = await crud.get_all_users(limit=20)
    if not users:
        await message.answer(ADMIN_NO_USERS_RU)
        return
    txt = ADMIN_USERS_HEADER_RU
    for u in users:
        txt += f"{u['user_id']} | {u['custom_name'] or '-'} | {u['age'] or '-'} | {u['service_id'] or '-'} | {u['source']} | @{u['username'] or '-'}\n"
    await message.answer(txt)
