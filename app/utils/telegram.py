"""
Небольшие помощники для работы с апдейтами Telegram.

Два типовых случая, на которых падали админские обработчики:

* ``callback_query.message`` может прийти как ``InaccessibleMessage``
  (сообщение старше 48 часов) — у него нет ``edit_text``/``answer``/``delete``;
* ``edit_text`` отвечает 400 «message is not modified», если админ нажал
  ту же кнопку второй раз.
"""
import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery


def cb_chat_id(cb: CallbackQuery) -> int | None:
    """
    ID чата колбека — доступен даже для InaccessibleMessage.

    Если не удалось определить и его, откатываемся на личку пользователя:
    лучше ответить не туда, чем промолчать.
    """
    message = getattr(cb, "message", None)
    chat = getattr(message, "chat", None)
    if chat is not None:
        return chat.id
    from_user = getattr(cb, "from_user", None)
    return from_user.id if from_user else None


async def edit_or_send(cb: CallbackQuery, text: str, reply_markup=None) -> bool:
    """
    Правит текст сообщения колбека, а если это невозможно — шлёт новое.

    Возвращает True, если сообщение доставлено (или менять было нечего).
    """
    chat_id = cb_chat_id(cb)
    try:
        await cb.message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        reason = str(e).lower()
        if "not modified" in reason:
            return True  # повторный клик по той же кнопке — менять нечего
        logging.warning(f"edit_text не удался ({e}), отправляю новым сообщением")
    except AttributeError as e:
        # InaccessibleMessage: у объекта нет edit_text
        logging.warning(f"Сообщение колбека недоступно для правки: {e}")

    if chat_id is None:
        return False
    try:
        await cb.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        logging.error(f"Не удалось ни отредактировать, ни отправить сообщение: {e}")
        return False


async def answer_callback(cb: CallbackQuery, text: str | None = None, show_alert: bool = False) -> None:
    """cb.answer(), который не роняет хендлер, если ответить уже нельзя."""
    try:
        await cb.answer(text, show_alert=show_alert)
    except Exception as e:  # noqa: BLE001 - ответ на колбек не критичен
        logging.debug(f"Не удалось ответить на колбек: {e}")


async def cb_send(cb: CallbackQuery, text: str, reply_markup=None) -> bool:
    """
    Отправляет сообщение в чат колбека.

    В отличие от ``cb.message.answer()`` работает и тогда, когда сообщение
    кнопки уже недоступно (InaccessibleMessage).
    """
    chat_id = cb_chat_id(cb)
    if chat_id is None:
        logging.warning("Не удалось определить чат колбека — сообщение не отправлено")
        return False
    await cb.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    return True


async def cb_reply(cb: CallbackQuery, text: str, reply_markup=None) -> bool:
    """
    Ответ в тот же тред, что и сообщение колбека.

    Откатывается на обычную отправку, если сообщение недоступно или удалено
    («message to reply not found») — раньше в таких случаях хендлер падал,
    а админ не получал ни счета, ни ошибки.
    """
    try:
        await cb.message.reply(text, reply_markup=reply_markup)
        return True
    except AttributeError as e:
        logging.warning(f"Сообщение колбека недоступно для ответа: {e}")
    except TelegramBadRequest as e:
        logging.warning(f"Не удалось ответить на сообщение колбека: {e}")
    return await cb_send(cb, text, reply_markup=reply_markup)
