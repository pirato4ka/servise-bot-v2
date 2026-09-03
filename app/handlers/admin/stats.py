from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app.database import crud
from app.data.texts import (
    ADMIN_STATS_TEXT_RU, ADMIN_NO_USERS_RU, ADMIN_USERS_HEADER_RU, ADMIN_REQ_NO_RIGHTS_RU
)

router = Router()


async def get_stats_text() -> str:
    s = await crud.get_stats()
    top_text = f"{s['top_service']} ({s['top_count']})" if s["top_service"] else "нет"
    return ADMIN_STATS_TEXT_RU.format(
        total=s["total"], today=s["today"], open_t=s["open_t"], top_text=top_text, paid_t=s["paid_t"]
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.chat.id != settings.ADMIN_CHAT_ID and not await crud.is_admin(message.from_user.id):
        return
    await message.answer(await get_stats_text())


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
        flag = "⛔" if u["is_banned"] else "✅"
        txt += (
            f"{flag} {u['user_id']} | {u['custom_name'] or '-'} | {u['age'] or '-'} | "
            f"{u['service_id'] or '-'} | {u['source']} | @{u['username'] or '-'}\n"
        )
    await message.answer(txt)
