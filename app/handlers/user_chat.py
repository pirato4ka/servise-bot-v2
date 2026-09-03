import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.config import settings
from app.database import crud
from app.data.texts import USER_CONTINUATION_TEMPLATE_RU

router = Router()


@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def user_free_message(message: Message, state: FSMContext):
    """Любое сообщение пользователя после анкеты улетает в админ-чат в тред заявки."""
    user_id = message.from_user.id

    if await state.get_state() is not None:
        return

    # Нажатие кнопки услуги — обрабатывается другим роутером
    if message.text:
        svc = await crud.get_service_by_button(message.text)
        if svc:
            return

    if await crud.is_banned(user_id):
        return

    ticket = await crud.get_last_ticket_by_user(user_id)
    user_row = await crud.get_user(user_id)

    if not ticket:
        if not user_row or not user_row["service_id"]:
            return
        # Заявки ещё нет (например, бот перезапускался) — создаём псевдо-тикет
        ticket = {
            "id": 0,
            "user_id": user_id,
            "admin_message_id": None,
            "service_id": user_row["service_id"],
        }

    service_row = await crud.get_service_by_id(
        (user_row["service_id"] if user_row and user_row["service_id"] else None) or ticket["service_id"] or "unknown"
    )
    lang = await crud.get_user_lang(user_id)
    service_title = (crud.localize_service(service_row, lang) or {}).get("title") or "Невідомо"
    custom_name = (user_row["custom_name"] if user_row and user_row["custom_name"] else None) or message.from_user.full_name
    username = f"@{message.from_user.username}" if message.from_user.username else "без username"

    text_content = message.text or message.caption or ""
    if not text_content:
        if message.photo:
            text_content = "📷 Фото"
        elif message.document:
            text_content = "📄 Документ"
        elif message.voice:
            text_content = "🎤 Голосове"
        else:
            text_content = "Повідомлення"

    reply_note = ""
    if message.reply_to_message:
        reply_note = "↩️ <b>(Відповідь на повідомлення адміністрації)</b>\n\n"

    admin_text = reply_note + USER_CONTINUATION_TEMPLATE_RU.format(
        name=custom_name,
        user_id=user_id,
        username=username,
        service_title=service_title,
        text=text_content[:1000],
    )

    reply_to = ticket["admin_message_id"] or None

    try:
        if message.photo:
            sent = await message.bot.send_photo(
                chat_id=settings.ADMIN_CHAT_ID,
                photo=message.photo[-1].file_id,
                caption=admin_text,
                reply_to_message_id=reply_to,
            )
        elif message.document:
            sent = await message.bot.send_document(
                chat_id=settings.ADMIN_CHAT_ID,
                document=message.document.file_id,
                caption=admin_text,
                reply_to_message_id=reply_to,
            )
        elif message.voice:
            sent = await message.bot.send_voice(
                chat_id=settings.ADMIN_CHAT_ID,
                voice=message.voice.file_id,
                reply_to_message_id=reply_to,
            )
            await message.bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=admin_text,
                reply_to_message_id=reply_to,
            )
        else:
            sent = await message.bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=admin_text,
                reply_to_message_id=reply_to,
            )

        # Запоминаем связь, чтобы админ мог ответить REPLY и на это сообщение
        if ticket["id"]:
            await crud.link_admin_message(sent.message_id, ticket["id"], reply_to)
        await crud.log_message(user_id, ticket["id"] or 0, "user_to_admin", text_content)

    except Exception as e:
        logging.error(f"USER_CHAT: forward error: {e}")
        try:
            await message.bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=admin_text + f"\n\n⚠️ Помилка reply: {e}",
            )
        except Exception:
            pass
