import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import settings
from app.database import crud
from app.data.texts import t
from app.keyboards.inline import get_agree_keyboard_localized
from app.keyboards.reply import get_services_keyboard
from app.utils.text import MESSAGE_LIMIT, esc, fit, strip_tags

router = Router()


class IsServiceButton(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not message.text or not message.from_user:
            return False
        if message.chat.id == settings.ADMIN_CHAT_ID:
            return False
        if message.text.startswith("/") or message.text in ("❌ Скасувати", "❌ Отменить"):
            return False
        # Ищем и выключенные услуги тоже: нажатие на устаревшую кнопку должно
        # получать внятный ответ, а не улетать в админ-чат как свободное сообщение.
        service = await crud.get_service_by_button(message.text, active_only=False)
        return service is not None


@router.message(IsServiceButton())
async def handle_service_choice(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return

    service_row = await crud.get_service_by_button(message.text, active_only=False)
    if not service_row:
        return

    lang = await crud.get_user_lang(message.from_user.id)

    if not service_row["is_active"]:
        logging.info(f"🔴 SERVICE: user={message.from_user.id} нажал выключенную услугу {service_row['id']}")
        kb = await get_services_keyboard(lang)
        await message.answer(t("service_inactive", lang), reply_markup=kb)
        return

    service = crud.localize_service(service_row, lang)
    logging.info(f"🟢 SERVICE: user={message.from_user.id} chose='{service['id']}' lang={lang}")

    # Название и описание вводит админ, но в интерфейсе пользователя это
    # просто текст — экранируем, чтобы «&» или «<» не роняли отправку.
    header = t("service_header", lang).format(
        emoji=esc(service["emoji"]),
        title=esc(service["title"]),
        short_desc=esc(service["short_desc"] or "")
    )
    footer = t("terms_footer", lang)
    kb = get_agree_keyboard_localized(service["id"], lang)
    terms = service["terms"] or ""
    full_text = fit(header + terms + footer, MESSAGE_LIMIT)

    try:
        await message.answer(full_text, reply_markup=kb)
    except TelegramBadRequest as e:
        # Условия услуги — это HTML, который админ набирает вручную.
        # При битой разметке Telegram отвечает 400, и пользователь оставался
        # с пустым экраном. Показываем условия как обычный текст.
        logging.warning(f"SERVICE: битый HTML в условиях услуги {service['id']}: {e}")
        plain_text = fit(header + esc(strip_tags(terms)) + footer, MESSAGE_LIMIT)
        try:
            await message.answer(plain_text, reply_markup=kb)
        except TelegramBadRequest:
            await message.answer(t("service_terms_broken", lang), reply_markup=kb)
