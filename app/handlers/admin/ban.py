"""
Блокировка клиентов.

Половина механизма уже была в проекте: `users.is_banned`, `crud.ban_user/unban_user`,
иконка ⛔ в `/users`, исключение забаненных из рассылки и тексты `banned_user` /
`unbanned_user`. Не хватало двух вещей: команды админа и запрета на новые заявки —
получалось, что флаг можно было выставить только руками в SQLite, и он ни на что
не влиял, кроме пересылки свободных сообщений.
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app.database import crud
from app.data.texts import t

router = Router()

USAGE_RU = (
    "Использование: <code>/ban &lt;user_id или @username&gt;</code>\n"
    "Снять блокировку: <code>/unban &lt;user_id или @username&gt;</code>"
)


async def resolve_target(message: Message) -> int | None:
    """
    Цель команды: числовой ID или @username из таблицы users.

    Возвращает None, если аргумент не задан или пользователь не найден
    (и сразу пишет админу причину).
    """
    args = (message.text or "").split()
    if len(args) < 2 or not args[1].strip():
        await message.reply(USAGE_RU)
        return None

    raw = args[1].strip().lstrip("@")
    if raw.isdigit():
        return int(raw)

    row = await crud.get_user_by_username(raw)
    if not row:
        await message.reply(f"❌ Пользователь <code>{raw}</code> не найден в базе. Нужен user_id.")
        return None
    return row["user_id"]


async def _notify_user(message: Message, user_id: int, key: str) -> None:
    """Сообщаем клиенту о смене статуса; если он заблокировал бота — не страшно."""
    try:
        lang = await crud.get_user_lang(user_id)
        await message.bot.send_message(chat_id=user_id, text=t(key, lang))
    except Exception as e:
        logging.info(f"BAN: не удалось уведомить {user_id} ({e})")


@router.message(Command("ban"), F.chat.id == settings.ADMIN_CHAT_ID)
async def ban_command(message: Message):
    if not message.from_user or not await crud.is_admin(message.from_user.id):
        await message.reply("⛔ Нет прав администратора")
        return

    user_id = await resolve_target(message)
    if user_id is None:
        return
    if user_id == message.from_user.id:
        await message.reply("❌ Заблокировать самого себя — плохая идея.")
        return

    await crud.ban_user(user_id)
    await _notify_user(message, user_id, "banned_user")
    await message.reply(f"⛔ Пользователь <code>{user_id}</code> заблокирован.\n"
                        f"Новые заявки и свободные сообщения от него не принимаются.")
    logging.info(f"BAN: {message.from_user.id} заблокировал {user_id}")


@router.message(Command("unban"), F.chat.id == settings.ADMIN_CHAT_ID)
async def unban_command(message: Message):
    if not message.from_user or not await crud.is_admin(message.from_user.id):
        await message.reply("⛔ Нет прав администратора")
        return

    user_id = await resolve_target(message)
    if user_id is None:
        return

    await crud.unban_user(user_id)
    await _notify_user(message, user_id, "unbanned_user")
    await message.reply(f"✅ Пользователь <code>{user_id}</code> разблокирован.")
    logging.info(f"BAN: {message.from_user.id} разблокировал {user_id}")
