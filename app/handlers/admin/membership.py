import logging

from aiogram import Bot, Router, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER

from app.config import settings
from app.database import crud
from app.data.texts import ADMIN_NEW_ADMIN_RU, ADMIN_REMOVE_ADMIN_RU
from app.utils.text import esc

router = Router()


async def sync_chat_admins(bot: Bot) -> tuple[int, int]:
    """
    Синхронизирует таблицу admins с реальным составом админ-чата.
    Вызывается при каждом запуске бота: после перезапуска все, кто уже есть
    в группе, остаются админами, даже если база пустая/новая.
    Возвращает (добавлено, удалено).
    """
    added = 0
    try:
        chat_admins = await bot.get_chat_administrators(settings.ADMIN_CHAT_ID)
    except Exception as e:
        logging.warning(f"MEMBERSHIP: не удалось получить администраторов чата: {e}")
        return added, 0

    actual_ids = set()
    for member in chat_admins:
        user = member.user
        if user.is_bot:
            continue
        actual_ids.add(user.id)
        if not await crud.is_admin(user.id):
            await crud.add_admin(user.id)
            added += 1
            logging.info(f"MEMBERSHIP: восстановлен админ {user.id} ({user.full_name})")

    # Убираем тех, кого бот видит как «left/kicked» (не трогаем, если проверить не удалось)
    removed = 0
    for admin in await crud.get_admins():
        uid = admin["user_id"]
        if uid in actual_ids:
            continue
        try:
            member = await bot.get_chat_member(settings.ADMIN_CHAT_ID, uid)
        except Exception:
            continue  # нет прав/сети — оставляем как есть, чтобы не терять админов
        if member.status in ("left", "kicked"):
            await crud.remove_admin(uid)
            removed += 1
            logging.info(f"MEMBERSHIP: удалён админ {uid} (status={member.status})")

    total = len(await crud.get_admins())
    logging.info(f"MEMBERSHIP: синхронизация завершена — всего админов: {total} (+{added}, -{removed})")
    return added, removed


@router.message(F.chat.id == settings.ADMIN_CHAT_ID, F.new_chat_members)
async def new_members_in_admin_chat(message: Message):
    added_by = message.from_user.id if message.from_user else None
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        await crud.add_admin(user.id, added_by=added_by)
        await message.answer(ADMIN_NEW_ADMIN_RU.format(name=esc(user.full_name), uid=user.id))


@router.message(F.chat.id == settings.ADMIN_CHAT_ID, F.left_chat_member)
async def left_member(message: Message):
    user = message.left_chat_member
    if user:
        await crud.remove_admin(user.id)
        await message.answer(ADMIN_REMOVE_ADMIN_RU.format(name=esc(user.full_name)))


@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER), F.chat.id == settings.ADMIN_CHAT_ID)
async def member_joined(event: ChatMemberUpdated):
    if event.new_chat_member.user.is_bot:
        return
    await crud.add_admin(event.new_chat_member.user.id, added_by=event.from_user.id if event.from_user else None)


@router.chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER), F.chat.id == settings.ADMIN_CHAT_ID)
async def member_left(event: ChatMemberUpdated):
    await crud.remove_admin(event.old_chat_member.user.id)


@router.message(F.chat.id == settings.ADMIN_CHAT_ID, ~F.reply_to_message)
async def auto_register_admin_on_message(message: Message):
    """Пишущий в админ-чат получает права автоматически (кроме служебных сообщений)."""
    # from_user отсутствует у постов из привязанного канала и части
    # сервисных сообщений — на них раньше падал AttributeError.
    if not message.from_user or message.from_user.is_bot:
        return
    if any(getattr(message, field, None) for field in ("pinned_message", "new_chat_members", "left_chat_member")):
        return
    # Fallback: сюда сообщение попадает, только если его не обработал ни один
    # роутер выше (включая шаги FSM-мастеров). Логируем — иначе «молчаливое
    # проглатывание» ввода не отличить от «обновление никто не обработал».
    preview = (message.text or message.caption or "")[:60].replace("\n", " ")
    if message.from_user.id and await crud.is_admin(message.from_user.id):
        logging.info(f"MEMBERSHIP: сообщение админа {message.from_user.id} не обработано роутерами: {preview!r}")
    if not await crud.is_admin(message.from_user.id):
        await crud.add_admin(message.from_user.id)
