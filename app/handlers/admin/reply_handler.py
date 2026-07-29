import logging
import re

from aiogram import Router, F
from aiogram.types import Message

from app.config import settings
from app.database import crud
from app.data.texts import t, ADMIN_SEND_ERROR_NO_TEXT_RU, ADMIN_SENT_OK_RU, ADMIN_SEND_FAIL_RU


router = Router()
router.message.filter(F.chat.id == settings.ADMIN_CHAT_ID, F.reply_to_message)


async def _find_user_id_from_message(msg) -> int | None:
    """Достаёт user_id из сообщения через entities (code) или regex по тексту"""
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


@router.message(F.reply_to_message)
async def admin_reply(message: Message):
    logging.info(f"🟡 REPLY_HANDLER: msg_id={message.message_id} reply_to={message.reply_to_message.message_id} text='{(message.text or '')[:50]}'")

    reply_to_id = message.reply_to_message.message_id
    ticket = await crud.get_ticket_by_admin_msg(reply_to_id)
    logging.info(f"🟡 REPLY_HANDLER: by admin_msg({reply_to_id}) = {'found' if ticket else 'NOT FOUND'}")

    # Способ 2: reply на продолжение — пробуем через родителя
    if not ticket and message.reply_to_message.reply_to_message:
        root_id = message.reply_to_message.reply_to_message.message_id
        ticket = await crud.get_ticket_by_admin_msg(root_id)
        logging.info(f"🟡 REPLY_HANDLER: second level root_id={root_id} = {'found' if ticket else 'NOT FOUND'}")

    # Способ 3: достаём user_id из текста/entities сообщения на которое reply
    if not ticket:
        uid = await _find_user_id_from_message(message.reply_to_message)
        if uid:
            ticket = await crud.get_last_ticket_by_user(uid)
            logging.info(f"🟡 REPLY_HANDLER: parsed uid={uid} from entities/text = {'found' if ticket else 'NOT FOUND'}")

    # Способ 4: пробуем из текста родительского сообщения
    if not ticket and message.reply_to_message.reply_to_message:
        uid = await _find_user_id_from_message(message.reply_to_message.reply_to_message)
        if uid:
            ticket = await crud.get_last_ticket_by_user(uid)
            logging.info(f"🟡 REPLY_HANDLER: parsed uid={uid} from parent = {'found' if ticket else 'NOT FOUND'}")

    if not ticket:
        logging.warning(f"🟡 REPLY_HANDLER: NO TICKET FOUND for reply_to={reply_to_id}")
        await message.reply("⚠️ Не удалось определить тикет. Попробуй reply на исходную заявку.")
        return

    user_id = ticket["user_id"]
    admin_text = message.text or message.caption or ""

    if not admin_text and not message.photo and not message.document and not message.voice:
        await message.reply(ADMIN_SEND_ERROR_NO_TEXT_RU)
        return

    try:
        await crud.log_message(user_id, ticket["id"], "admin_to_user", admin_text)
    except:
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
            await message.bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=reply_text.format(admin_text=admin_text) if admin_text else "💬 " + ("Відповідь від адміністрації" if lang == "ua" else "Ответ от администрации")
            )
        elif message.document:
            await message.bot.send_document(chat_id=user_id, document=message.document.file_id, caption=admin_text)
        elif message.voice:
            await message.bot.send_voice(chat_id=user_id, voice=message.voice.file_id)
            if admin_text:
                await message.bot.send_message(chat_id=user_id, text=reply_text.format(admin_text=admin_text))

        logging.info(f"🟡 REPLY_HANDLER: sent to user {user_id} OK")
        await message.reply(ADMIN_SENT_OK_RU.format(uid=user_id))

    except Exception as e:
        logging.error(f"🟡 REPLY_HANDLER: send error: {e}")
        await message.reply(ADMIN_SEND_FAIL_RU.format(e=e))
