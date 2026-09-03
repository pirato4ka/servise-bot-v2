import logging
import re
from datetime import datetime
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.config import settings
from app.database import crud
from app.database.db import get_db
from app.data.texts import t, ADMIN_TEMPLATE_RU
from app.keyboards.reply import get_cancel_keyboard, get_recipient_keyboard, get_services_keyboard
from app.keyboards.inline import admin_ticket_kb
from app.states.questionnaire import Questionnaire
from app.utils.telegram import answer_callback, cb_send
from app.utils.text import MESSAGE_LIMIT, esc, fit

router = Router()

# Шаг 3/3 — «кому требуется услуга». Канонические значения + допустимые варианты написания.
RECIPIENT_VARIANTS = {
    "me": {"мне", "мені", "мні", "me", "себе", "собі", "себя", "я", "самому", "самій"},
    "relative": {"родному", "рідному", "родным", "родній", "родственнику", "родичу", "relative", "семье", "сім'ї"},
    "friend": {"другу", "друг", "подруге", "подрузі", "friend", "знакомому", "знайомому"},
}
RECIPIENT_LABELS_RU = {"me": "Мне", "relative": "Родному", "friend": "Другу"}

MIN_AGE = 16
MAX_AGE = 99


def normalize_recipient(text: Optional[str]) -> Optional[str]:
    """Принимает 'Мне', '👤 Мне', 'мне please' -> 'me'. Иначе None."""
    if not text:
        return None
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    for token in cleaned.split():
        for key, variants in RECIPIENT_VARIANTS.items():
            if token in variants:
                return key
    return None


def recipient_label(key: Optional[str]) -> str:
    return RECIPIENT_LABELS_RU.get(key or "", key or "—")


def _is_cancel(text: Optional[str]) -> bool:
    return text in ("❌ Скасувати", "❌ Отменить")


async def _abort(message: Message, state: FSMContext, lang: str):
    await state.clear()
    # Клавиатура — на языке пользователя: раньше после отмены русскоязычный
    # клиент получал украинские кнопки.
    kb = await get_services_keyboard(lang)
    await message.answer(t("cancel_message", lang), reply_markup=kb)


@router.callback_query(F.data.startswith("agree:"))
async def agree_handler(callback: CallbackQuery, state: FSMContext):
    service_id = callback.data.split(":", 1)[1]
    service = await crud.get_service_by_id(service_id)
    if not service:
        await answer_callback(callback, "Послугу не знайдено", show_alert=True)
        return

    lang = await crud.get_user_lang(callback.from_user.id)

    # Заблокированный клиент не должен создавать новые заявки: раньше флаг
    # is_banned глушил только свободные сообщения в user_chat.
    if await crud.is_banned(callback.from_user.id):
        await answer_callback(callback)
        await cb_send(callback, t("banned_user", lang))
        return

    # Услугу могли выключить в админке уже после того, как пользователь
    # увидел кнопку — не пускаем в анкету по неактивной услуге.
    if not service["is_active"]:
        await state.clear()
        kb = await get_services_keyboard(lang)
        await cb_send(callback, t("service_inactive", lang), reply_markup=kb)
        await answer_callback(callback)
        return

    await state.clear()
    await state.update_data(selected_service_id=service_id)
    await state.set_state(Questionnaire.waiting_for_name)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb_send(callback, t("questionnaire_start", lang))
    await cb_send(callback, t("ask_name", lang), reply_markup=get_cancel_keyboard(lang))
    await answer_callback(callback)


@router.message(Questionnaire.waiting_for_name, F.text)
async def q_name(message: Message, state: FSMContext):
    lang = await crud.get_user_lang(message.from_user.id)
    if _is_cancel(message.text):
        await _abort(message, state, lang)
        return
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(t("invalid_name", lang), reply_markup=get_cancel_keyboard(lang))
        return
    await state.update_data(name=name)
    await state.set_state(Questionnaire.waiting_for_age)
    await message.answer(t("ask_age", lang), reply_markup=get_cancel_keyboard(lang))


@router.message(Questionnaire.waiting_for_age, F.text)
async def q_age(message: Message, state: FSMContext):
    lang = await crud.get_user_lang(message.from_user.id)
    if _is_cancel(message.text):
        await _abort(message, state, lang)
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(t("invalid_age", lang), reply_markup=get_cancel_keyboard(lang))
        return
    age = int(raw)
    if not MIN_AGE <= age <= MAX_AGE:
        await message.answer(t("invalid_age", lang), reply_markup=get_cancel_keyboard(lang))
        return
    await state.update_data(age=age)
    await state.set_state(Questionnaire.waiting_for_recipient)
    await message.answer(t("ask_recipient", lang), reply_markup=get_recipient_keyboard(lang))


@router.message(Questionnaire.waiting_for_recipient, F.text)
async def q_recipient(message: Message, state: FSMContext):
    lang = await crud.get_user_lang(message.from_user.id)
    if _is_cancel(message.text):
        await _abort(message, state, lang)
        return

    recipient_key = normalize_recipient(message.text)
    if not recipient_key:
        await message.answer(t("invalid_recipient", lang), reply_markup=get_recipient_keyboard(lang))
        return

    await state.update_data(recipient=recipient_key)
    data = await state.get_data()
    service = await crud.get_service_by_id(data["selected_service_id"])
    if not service:
        await _abort(message, state, lang)
        return

    # Страховка: если пользователя нет в users (например, бот не видел /start),
    # заявка не создалась бы из-за внешнего ключа.
    await crud.upsert_user(
        message.from_user.id, message.from_user.username or "", message.from_user.full_name or ""
    )
    await crud.update_user_questionnaire(
        message.from_user.id, data["name"], data["age"], recipient_key, service["id"]
    )

    db = await get_db()
    try:
        async with db.execute("SELECT * FROM users WHERE user_id=?", (message.from_user.id,)) as cur:
            user_row = await cur.fetchone()
    finally:
        await db.close()
    source = user_row["source"] if user_row else "direct"
    username = f"@{message.from_user.username}" if message.from_user.username else "нет username"
    # Имя, username и источник приходят от пользователя: без экранирования
    # «Tom & Jerry» в имени ронял отправку (parse_mode=HTML) и заявка
    # терялась молча, а клиенту приходило «Заявку прийнято».
    mention = f"<a href='tg://user?id={message.from_user.id}'>{esc(data['name'])}</a>"

    admin_text = fit(
        ADMIN_TEMPLATE_RU,
        MESSAGE_LIMIT,
        date=datetime.now().strftime("%d.%m.%Y %H:%M"),
        name=esc(data["name"]),
        age=data["age"],
        recipient=recipient_label(recipient_key),
        service_title=esc(service["title_ru"] or service["title_ua"]),
        service_id=esc(service["id"]),
        source=esc(source),
        lang=lang.upper(),
        user_mention=mention,
        user_id=message.from_user.id,
        username=esc(username),
    )

    ticket_created = False
    try:
        sent = await message.bot.send_message(chat_id=settings.ADMIN_CHAT_ID, text=admin_text)
        ticket_id = await crud.create_ticket(
            message.from_user.id, sent.message_id, settings.ADMIN_CHAT_ID, service["id"]
        )
        await crud.log_message(
            message.from_user.id, ticket_id, "user_to_admin", f"анкета: {data}"
        )
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=settings.ADMIN_CHAT_ID,
                message_id=sent.message_id,
                reply_markup=admin_ticket_kb(sent.message_id),
            )
        except Exception as e:
            # Заявка уже в чате — отсутствие кнопок не повод терять анкету
            logging.warning(f"Не удалось добавить кнопки к заявке: {e}")
        ticket_created = True
    except Exception as e:
        logging.error(f"Admin send error: {e}")

    kb = await get_services_keyboard(lang)
    if ticket_created:
        await message.answer(t("final_message", lang), reply_markup=kb)
        await state.clear()
    else:
        # Честно сообщаем о сбое: иначе клиент ждёт ответа, которого не существует.
        await message.answer(t("ticket_send_error", lang), reply_markup=kb)
        await state.clear()
