import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime

from app.states.questionnaire import Questionnaire
from app.data.texts import t, ADMIN_TEMPLATE_RU
from app.database import crud
from app.database.db import get_db
from app.keyboards.reply import get_cancel_keyboard, get_services_keyboard
from app.keyboards.inline import admin_ticket_kb, get_agree_keyboard_localized
from app.config import settings

router = Router()


@router.callback_query(F.data.startswith("agree:"))
async def agree_handler(callback: CallbackQuery, state: FSMContext):
    service_id = callback.data.split(":", 1)[1]
    service = await crud.get_service_by_id(service_id)
    if not service:
        await callback.answer("Послугу не знайдено", show_alert=True)
        return

    lang = await crud.get_user_lang(callback.from_user.id)

    await state.update_data(selected_service_id=service_id)
    await state.set_state(Questionnaire.waiting_for_name)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer(t("questionnaire_start", lang))
    await callback.message.answer(t("ask_name", lang), reply_markup=get_cancel_keyboard(lang))
    await callback.answer()


@router.message(Questionnaire.waiting_for_name, F.text)
async def q_name(message: Message, state: FSMContext):
    lang = await crud.get_user_lang(message.from_user.id)
    if message.text in ("❌ Скасувати", "❌ Отменить"):
        await state.clear()
        kb = await get_services_keyboard()
        await message.answer(t("cancel_message", lang), reply_markup=kb)
        return
    if len(message.text.strip()) < 2:
        await message.answer("⚠️" if lang == "ua" else "⚠️ Укажите корректно")
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(Questionnaire.waiting_for_age)
    await message.answer(t("ask_age", lang), reply_markup=get_cancel_keyboard(lang))


@router.message(Questionnaire.waiting_for_age, F.text)
async def q_age(message: Message, state: FSMContext):
    lang = await crud.get_user_lang(message.from_user.id)
    if message.text in ("❌ Скасувати", "❌ Отменить"):
        await state.clear()
        kb = await get_services_keyboard()
        await message.answer(t("cancel_message", lang), reply_markup=kb)
        return
    if not message.text.isdigit():
        await message.answer(t("invalid_age", lang), reply_markup=get_cancel_keyboard(lang))
        return
    age = int(message.text)
    if not 16 <= age <= 99:
        await message.answer(t("invalid_age", lang), reply_markup=get_cancel_keyboard(lang))
        return
    await state.update_data(age=age)
    await state.set_state(Questionnaire.waiting_for_plan_date)
    await message.answer(t("ask_plan_date", lang), reply_markup=get_cancel_keyboard(lang))


@router.message(Questionnaire.waiting_for_plan_date, F.text)
async def q_date(message: Message, state: FSMContext):
    lang = await crud.get_user_lang(message.from_user.id)
    if message.text in ("❌ Скасувати", "❌ Отменить"):
        await state.clear()
        kb = await get_services_keyboard()
        await message.answer(t("cancel_message", lang), reply_markup=kb)
        return

    await state.update_data(plan_date=message.text.strip())
    data = await state.get_data()
    service = await crud.get_service_by_id(data["selected_service_id"])

    await crud.update_user_questionnaire(message.from_user.id, data["name"], data["age"], data["plan_date"], service["id"])

    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE user_id=?", (message.from_user.id,)) as cur:
        user_row = await cur.fetchone()
    await db.close()
    source = user_row["source"] if user_row else "direct"
    username = f"@{message.from_user.username}" if message.from_user.username else "нет username"
    mention = f"<a href='tg://user?id={message.from_user.id}'>{data['name']}</a>"

    admin_text = ADMIN_TEMPLATE_RU.format(
        date=datetime.now().strftime("%d.%m.%Y %H:%M"),
        name=data["name"],
        age=data["age"],
        plan_date=data["plan_date"],
        service_title=service["title"],
        service_id=service["id"],
        source=source,
        lang=lang.upper(),
        user_mention=mention,
        user_id=message.from_user.id,
        username=username
    )
    try:
        sent = await message.bot.send_message(chat_id=settings.ADMIN_CHAT_ID, text=admin_text)
        ticket_id = await crud.create_ticket(message.from_user.id, sent.message_id, settings.ADMIN_CHAT_ID, service["id"])
        await crud.log_message(message.from_user.id, ticket_id, "user_to_admin", f"{data}")

        await message.bot.edit_message_reply_markup(
            chat_id=settings.ADMIN_CHAT_ID,
            message_id=sent.message_id,
            reply_markup=admin_ticket_kb(sent.message_id)
        )
    except Exception as e:
        logging.error(f"Admin send error: {e}")

    kb = await get_services_keyboard()
    await message.answer(t("final_message", lang), reply_markup=kb)
    await state.clear()
