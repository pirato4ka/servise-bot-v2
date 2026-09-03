from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app.database import crud
from app.data.texts import (
    ADMIN_NO_USERS_RU,
    ADMIN_REQ_NO_RIGHTS_RU,
    ADMIN_STATS_TEXT_RU,
    ADMIN_USERS_HEADER_RU,
)
from app.utils.text import MESSAGE_LIMIT, esc, truncate

router = Router()


async def get_stats_text() -> str:
    s = await crud.get_stats()
    top_text = f"{s['top_service']} ({s['top_count']})" if s["top_service"] else "нет"
    return ADMIN_STATS_TEXT_RU.format(
        total=s["total"], today=s["today"], open_t=s["open_t"], top_text=esc(top_text), paid_t=s["paid_t"]
    )


def _user_line(u: dict) -> str:
    """Строка списка пользователей. Имя приходит из анкеты — экранируем."""
    flag = "⛔" if u.get("is_banned") else "✅"
    return (
        f"{flag} {u['user_id']} | {esc(u['custom_name'] or '-')} | {esc(u['age'] or '-')} | "
        f"{esc(u['service_id'] or '-')} | {esc(u['source'])} | @{esc(u['username'] or '-')}\n"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not message.from_user:  # пост из канала
        return
    if message.chat.id != settings.ADMIN_CHAT_ID and not await crud.is_admin(message.from_user.id):
        await message.answer(ADMIN_REQ_NO_RIGHTS_RU)
        return
    await message.answer(await get_stats_text())


@router.message(Command("users"))
async def cmd_users(message: Message):
    if not message.from_user:  # пост из канала
        return
    if message.chat.id != settings.ADMIN_CHAT_ID and not await crud.is_admin(message.from_user.id):
        await message.answer(ADMIN_REQ_NO_RIGHTS_RU)
        return
    users = await crud.get_all_users(limit=20)
    if not users:
        await message.answer(ADMIN_NO_USERS_RU)
        return

    # Собираем по частям и режем под лимит Telegram: одно длинное имя
    # не должно ронять весь список.
    text = ADMIN_USERS_HEADER_RU
    for u in users:
        line = _user_line(u)
        if len(text) + len(line) > MESSAGE_LIMIT:
            text = truncate(text, MESSAGE_LIMIT - 20) + "\n…"
            break
        text += line
    await message.answer(text)
