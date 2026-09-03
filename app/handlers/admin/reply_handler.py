import logging
import re

from aiogram import Router, F
from aiogram.types import Message

from app.config import settings
from app.database import crud
from app.data.texts import t, ADMIN_SEND_ERROR_NO_TEXT_RU, ADMIN_SENT_OK_RU, ADMIN_SEND_FAIL_RU

router = Router()
router.message.filter(F.chat.id == settings.ADMIN_CHAT_ID, F.reply_to_message)

# Служебные сообщения Telegram (в т.ч. закрепление) приходят как reply на сообщение,
# поэтому раньше на каждый пин бот отвечал «⚠️ Не удалось определить тикет».
SERVICE_FIELDS = (
    "pinned_message",
    "new_chat_members",
    "left_chat_member",
    "new_chat_title",
    "new_chat_photo",
    "delete_chat_photo",
    "group_chat_created",
    "supergroup_chat_created",
    "channel_chat_created",
    "migrate_to_chat_id",
    "migrate_from_chat_id",
    "message_auto_delete_timer_changed",
    "video_chat_started",
    "video_chat_ended",
    "video_chat_scheduled",
    "video_chat_participants_invited",
    "forum_topic_created",
    "forum_topic_closed",
    "forum_topic_reopened",
    "forum_topic_edited",
    "general_forum_topic_hidden",
    "general_forum_topic_unhidden",
    "write_access_allowed",
    "successful_payment",
    "connected_website",
)


def is_service_message(message: Message) -> bool:
    return any(getattr(message, field, None) for field in SERVICE_FIELDS)


async def _find_user_id_from_message(msg) -> int | None:
    """Достаём user_id из сообщения через entities (code) или regex по тексту."""
    if not msg:
        return None

    text = msg.text or msg.caption or ""

    # Способ 1: через entities (code-блоки содержат user_id)
    entities = msg.entities or msg.caption_entities or []
    for entity in entities:
        if entity.type == "code":
            code_text = text[entity.offset:entity.offset + entity.length]
            if code_text.isdigit() and len(code_text) >= 5:
                return int(code_text)

    # Способ 2: regex по чистому тексту (ищем число 5+ цифр после 🆔)
    m = re.search(r"🆔\s*(\d{5,})", text)
    if m:
        return int(m.group(1))

    # Способ 3: просто первое длинное число
    m = re.search(r"(\d{7,})", text)
    if m:
        return int(m.group(1))

    return None


async def _resolve_ticket(message: Message):
    """Ищем заявку: сначала по карте сообщений (любая вложенность), затем эвристики."""
    reply_to_id = message.reply_to_message.message_id

    ticket = await crud.resolve_ticket_by_admin_message(reply_to_id)
    if ticket:
        return ticket

    parent = message.reply_to_message.reply_to_message
    if parent:
        ticket = await crud.resolve_ticket_by_admin_message(parent.message_id)
        if ticket:
            return ticket

    for source in (message.reply_to_message, parent):
        uid = await _find_user_id_from_message(source)
        if uid:
            ticket = await crud.get_last_ticket_by_user(uid)
            if ticket:
                return ticket

    return None


@router.message()
async def admin_reply(message: Message):
    # Закрепление, вход/выход участников и прочие служебные события не должны
    # восприниматься как ответ на заявку.
    if is_service_message(message):
        logging.debug(f"REPLY_HANDLER: skip service message {message.content_type}")
        return

    reply_to_id = message.reply_to_message.message_id
    ticket = await _resolve_ticket(message)

    if not ticket:
        logging.warning(f"REPLY_HANDLER: NO TICKET FOUND for reply_to={reply_to_id}")
        await message.reply("⚠️ Не удалось определить тикет. Попробуй reply на исходную заявку.")
        return

    user_id = ticket["user_id"]
    admin_text = message.text or message.caption or ""

    if not admin_text and not message.photo and not message.document and not message.voice:
        await message.reply(ADMIN_SEND_ERROR_NO_TEXT_RU)
        return

    try:
        await crud.log_message(user_id, ticket["id"], "admin_to_user", admin_text)
    except Exception:
        pass

    try:
        lang = await crud.get_user_lang(user_id)
        reply_text = t("admin_reply_to_user", lang)

        if message.text:
            await message.bot.send_message(
                chat_id=user_id,
                text=reply_text.format(admin_text=admin_text)
            )
        elif message.photo:
            caption = reply_text.format(admin_text=admin_text) if admin_text else (
                "💬 " + ("Відповідь від адміністрації" if lang == "ua" else "Ответ от администрации")
            )
            await message.bot.send_photo(chat_id=user_id, photo=message.photo[-1].file_id, caption=caption)
        elif message.document:
            await message.bot.send_document(chat_id=user_id, document=message.document.file_id, caption=admin_text)
        elif message.voice:
            await message.bot.send_voice(chat_id=user_id, voice=message.voice.file_id)
            if admin_text:
                await message.bot.send_message(chat_id=user_id, text=reply_text.format(admin_text=admin_text))

        # Запоминаем ответ админа, чтобы reply на reply тоже находил заявку
        await crud.link_admin_message(message.message_id, ticket["id"], reply_to_id)

        logging.info(f"REPLY_HANDLER: sent to user {user_id} OK")
        await message.reply(ADMIN_SENT_OK_RU.format(uid=user_id))

    except Exception as e:
        logging.error(f"REPLY_HANDLER: send error: {e}")
        await message.reply(ADMIN_SEND_FAIL_RU.format(e=e))
