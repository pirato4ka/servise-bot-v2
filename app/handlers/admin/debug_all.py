import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

router = Router()
router.message.filter(F.chat.type.in_(["group", "supergroup"]))


# Ловит ВСЕ колбеки и пишет в лог — чтобы понять доходят ли кнопки.
# Подключается только при DEBUG_ALL=1 (см. app.bot.build_dispatcher),
# иначе необработанные кнопки висели бы «часиками» без cb.answer().
@router.callback_query()
async def debug_all_callbacks(cb: CallbackQuery):
    logging.debug(
        f"🔍 CALLBACK: data={cb.data} | from={cb.from_user.id} | "
        f"chat={cb.message.chat.id if cb.message else 'no-chat'}"
    )
    await cb.answer()  # обязательно снимаем «часики» с кнопки


@router.message()
async def debug_all_messages(message: Message):
    logging.debug(
        f"🔍 MESSAGE: chat={message.chat.id} | from={message.from_user.id} | "
        f"content_type={message.content_type} | reply_to="
        f"{message.reply_to_message.message_id if message.reply_to_message else 'NO_REPLY'}"
    )
