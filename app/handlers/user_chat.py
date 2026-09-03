import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import settings
from app.database import crud
from app.data.texts import USER_CONTINUATION_TEMPLATE_RU, USER_MEDIA_CAPTION_RU, t
from app.middlewares.throttling import ThrottlingMiddleware
from app.utils.text import CAPTION_LIMIT, MESSAGE_LIMIT, esc, fit

router = Router()

# Антифлуд: каждое свободное сообщение клиента пересылается в админ-чат,
# поэтому поток сообщений от одного пользователя ограничиваем именно здесь.
# Анкета, кнопки услуг и админ-чат не затрагиваются.
throttling = ThrottlingMiddleware()
router.message.middleware(throttling)


@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def user_free_message(message: Message, state: FSMContext):
    """Любое сообщение пользователя после анкеты улетает в админ-чат в тред заявки."""
    if not message.from_user:  # анонимные/служебные сообщения
        return

    user_id = message.from_user.id

    if await state.get_state() is not None:
        return

    # Нажатие кнопки услуги (в том числе выключенной) — обрабатывается другим роутером
    if message.text:
        svc = await crud.get_service_by_button(message.text, active_only=False)
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
        elif message.video:
            text_content = "🎬 Відео"
        elif message.audio:
            text_content = "🎧 Аудіо"
        elif message.animation:
            text_content = "🎞 Анімація"
        elif message.sticker:
            text_content = "😀 Стикер"
        elif message.video_note:
            text_content = "🎥 Кругове відео"
        else:
            text_content = "Повідомлення"

    reply_note = ""
    if message.reply_to_message:
        reply_note = "↩️ <b>(Відповідь на повідомлення адміністрації)</b>\n\n"

    # Всё, что пришло от пользователя, экранируется: parse_mode=HTML, и один
    # символ «<» в тексте клиента раньше ронял отправку — сообщение терялось.
    template_values = {
        "name": esc(custom_name),
        "user_id": user_id,
        "username": esc(username),
        "service_title": esc(service_title),
    }
    admin_text = fit(
        reply_note + USER_CONTINUATION_TEMPLATE_RU,
        MESSAGE_LIMIT,
        text=esc(text_content),
        **template_values,
    )
    reply_to = ticket["admin_message_id"] or None

    sent_ids: list[int] = []
    try:
        if message.photo:
            sent_ids += await _send_media(
                message, admin_text, reply_to, template_values,
                send=lambda **kw: message.bot.send_photo(
                    chat_id=settings.ADMIN_CHAT_ID, photo=message.photo[-1].file_id, **kw
                ),
            )
        elif message.document:
            sent_ids += await _send_media(
                message, admin_text, reply_to, template_values,
                send=lambda **kw: message.bot.send_document(
                    chat_id=settings.ADMIN_CHAT_ID, document=message.document.file_id, **kw
                ),
            )
        elif message.voice:
            sent_ids += await _send_media(
                message, admin_text, reply_to, template_values,
                send=lambda **kw: message.bot.send_voice(
                    chat_id=settings.ADMIN_CHAT_ID, voice=message.voice.file_id, **kw
                ),
            )
        elif message.video:
            sent_ids += await _send_media(
                message, admin_text, reply_to, template_values,
                send=lambda **kw: message.bot.send_video(
                    chat_id=settings.ADMIN_CHAT_ID, video=message.video.file_id, **kw
                ),
            )
        elif message.audio:
            sent_ids += await _send_media(
                message, admin_text, reply_to, template_values,
                send=lambda **kw: message.bot.send_audio(
                    chat_id=settings.ADMIN_CHAT_ID, audio=message.audio.file_id, **kw
                ),
            )
        elif message.animation:
            sent_ids += await _send_media(
                message, admin_text, reply_to, template_values,
                send=lambda **kw: message.bot.send_animation(
                    chat_id=settings.ADMIN_CHAT_ID, animation=message.animation.file_id, **kw
                ),
            )
        elif message.sticker or message.video_note:
            # Эти типы Telegram не поддерживают подпись: сначала медиа, затем
            # полный текст (с именем/услугой/данными клиента) в тот же тред.
            if message.sticker:
                sent = await message.bot.send_sticker(
                    chat_id=settings.ADMIN_CHAT_ID, sticker=message.sticker.file_id,
                    reply_to_message_id=reply_to,
                )
            else:
                sent = await message.bot.send_video_note(
                    chat_id=settings.ADMIN_CHAT_ID, video_note=message.video_note.file_id,
                    reply_to_message_id=reply_to,
                )
            sent_ids.append(sent.message_id)
            follow_up = await message.bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID, text=admin_text, reply_to_message_id=reply_to,
            )
            sent_ids.append(follow_up.message_id)
        else:
            sent = await message.bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=admin_text,
                reply_to_message_id=reply_to,
            )
            sent_ids.append(sent.message_id)

        # Запоминаем связь, чтобы админ мог ответить REPLY и на это сообщение
        if ticket["id"]:
            for message_id in sent_ids:
                await crud.link_admin_message(message_id, ticket["id"], reply_to)
        await crud.log_message(user_id, ticket["id"] or 0, "user_to_admin", text_content)

    except Exception as e:
        logging.error(f"USER_CHAT: forward error: {e}")
        try:
            await message.bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                # admin_text уже собран (и может содержать фигурные скобки
                # из текста клиента) — поэтому конкатенация, а не .format()
                text=fit(admin_text + "\n\n⚠️ Помилка reply: " + esc(e), MESSAGE_LIMIT),
            )
        except Exception as inner:
            # В админ-чат не уходит вообще ничего — говорим об этом клиенту,
            # иначе он будет ждать ответа, которого не существует.
            logging.error(f"USER_CHAT: fallback тоже не удался: {inner}")
            try:
                await message.answer(t("ticket_send_error", lang))
            except Exception as notify_error:
                logging.error(f"USER_CHAT: не удалось предупредить клиента: {notify_error}")


async def _send_media(message: Message, admin_text: str, reply_to,
                      template_values: dict, send) -> list[int]:
    """
    Шлёт медиа в админ-чат.

    Подпись Telegram ограничена 1024 символами, а полный шаблон с текстом
    клиента легко её превышает. Раньше это давало 400 «caption is too long»,
    и медиа терялось целиком. Теперь: если текст влезает — шлём одной
    подписью, иначе короткая шапка на медиа + полный текст отдельным
    сообщением в тот же тред.
    """
    if len(admin_text) <= CAPTION_LIMIT:
        sent = await send(caption=admin_text, reply_to_message_id=reply_to)
        return [sent.message_id]

    short_caption = fit(USER_MEDIA_CAPTION_RU, CAPTION_LIMIT, **template_values)
    sent = await send(caption=short_caption, reply_to_message_id=reply_to)
    follow_up = await message.bot.send_message(
        chat_id=settings.ADMIN_CHAT_ID, text=admin_text, reply_to_message_id=reply_to
    )
    return [sent.message_id, follow_up.message_id]
