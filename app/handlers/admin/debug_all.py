from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
import logging

router = Router()

# Ловит ВСЕ колбеки и пишет в лог — чтобы понять доходят ли кнопки
@router.callback_query()
async def debug_all_callbacks(cb: CallbackQuery):
    logging.info(f"🔍 CALLBACK DEBUG: data={cb.data} | from={cb.from_user.id} | chat={cb.message.chat.id if cb.message else 'no-chat'} | msg_id={cb.message.message_id if cb.message else 'no-msg'}")
    # не делаем answer, чтобы другие хендлеры тоже сработали
    # но для теста отвечаем
    # await cb.answer()

# Ловит ВСЕ сообщения в админ-чате
@router.message()
async def debug_all_messages(message: Message):
    from app.config import settings
    if message.chat.id != settings.ADMIN_CHAT_ID:
        return
    logging.info(f"🔍 MESSAGE DEBUG: chat={message.chat.id} | from={message.from_user.id} | text={message.text[:100] if message.text else 'NO_TEXT'} | reply_to={message.reply_to_message.message_id if message.reply_to_message else 'NO_REPLY'} | content_type={message.content_type}")
