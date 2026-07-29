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
    logging.info(f"🔵 USER_CHAT: user={message.from_user.id} text='{(message.text or '')[:50]}' reply_to={message.reply_to_message.message_id if message.reply_to_message else 'NO'} content={message.content_type}")
    
    current_state = await state.get_state()
    if current_state is not None:
        logging.info(f"🔵 USER_CHAT: SKIP — FSM state={current_state}")
        return

    # Проверяем что это не нажатие кнопки услуги
    if message.text:
        svc = await crud.get_service_by_button(message.text)
        if svc:
            logging.info(f"🔵 USER_CHAT: SKIP — matched service button '{message.text}'")
            return

    # Берём ПОСЛЕДНИЙ тикет (не только open, но и invoice_sent, paid — для реплаев после подтверждения)
    ticket = await crud.get_last_ticket_by_user(message.from_user.id)
    if not ticket:
        logging.info(f"🔵 USER_CHAT: no ticket found, checking user...")
        from app.database.db import get_db
        db = await get_db()
        async with db.execute("SELECT * FROM users WHERE user_id=?", (message.from_user.id,)) as cur:
            u = await cur.fetchone()
        await db.close()
        if not u or not u["service_id"]:
            logging.info(f"🔵 USER_CHAT: SKIP — no user/service")
            return
        # Если тикета вообще нет — создаём псевдо-тикет
        ticket = {"admin_message_id": None, "service_id": u["service_id"], "id": 0, "user_id": message.from_user.id}

    logging.info(f"🔵 USER_CHAT: ticket found — id={ticket['id']} admin_msg={ticket['admin_message_id']}")

    from app.database.db import get_db
    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE user_id=?", (message.from_user.id,)) as cur:
        user_row = await cur.fetchone()
    async with db.execute("SELECT title FROM services WHERE id=?", (user_row["service_id"] if user_row and user_row["service_id"] else "unknown",)) as cur:
        s_title_row = await cur.fetchone()
    await db.close()

    service_title = s_title_row["title"] if s_title_row else "Невідомо"
    custom_name = user_row["custom_name"] if user_row and user_row["custom_name"] else message.from_user.full_name
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

    # Если это reply на сообщение бота — добавляем пометку
    reply_note = ""
    if message.reply_to_message:
        reply_note = "↩️ <b>(Відповідь на повідомлення адміністрації)</b>\n\n"

    admin_text = reply_note + USER_CONTINUATION_TEMPLATE_RU.format(
        name=custom_name,
        user_id=message.from_user.id,
        username=username,
        service_title=service_title,
        text=text_content[:1000]
    )

    try:
        reply_to = ticket["admin_message_id"] if ticket["admin_message_id"] else None

        if message.text:
            sent = await message.bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=admin_text,
                reply_to_message_id=reply_to
            )
        elif message.photo:
            sent = await message.bot.send_photo(
                chat_id=settings.ADMIN_CHAT_ID,
                photo=message.photo[-1].file_id,
                caption=admin_text,
                reply_to_message_id=reply_to
            )
        elif message.document:
            sent = await message.bot.send_document(
                chat_id=settings.ADMIN_CHAT_ID,
                document=message.document.file_id,
                caption=admin_text,
                reply_to_message_id=reply_to
            )
        elif message.voice:
            sent = await message.bot.send_voice(
                chat_id=settings.ADMIN_CHAT_ID,
                voice=message.voice.file_id,
                reply_to_message_id=reply_to
            )
            await message.bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=admin_text,
                reply_to_message_id=reply_to
            )
        else:
            sent = await message.bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=admin_text,
                reply_to_message_id=reply_to
            )

        logging.info(f"🔵 USER_CHAT: forwarded to admin chat, msg_id={sent.message_id}")

        await crud.log_message(message.from_user.id, ticket["id"] if "id" in ticket else 0, "user_to_admin", text_content)

    except Exception as e:
        logging.error(f"🔵 USER_CHAT: forward error: {e}")
        try:
            await message.bot.send_message(chat_id=settings.ADMIN_CHAT_ID, text=admin_text + f"\n\n⚠️ Помилка reply: {e}")
        except:
            pass
