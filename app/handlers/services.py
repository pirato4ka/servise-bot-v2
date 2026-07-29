import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import BaseFilter

from app.database import crud
from app.data.texts import t
from app.keyboards.inline import get_agree_keyboard_localized
from app.config import settings


router = Router()


class IsServiceButton(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not message.text:
            return False
        if message.chat.id == settings.ADMIN_CHAT_ID:
            return False
        if message.text.startswith("/") or message.text in ("❌ Скасувати", "❌ Отменить"):
            return False
        service = await crud.get_service_by_button(message.text)
        return service is not None


@router.message(IsServiceButton())
async def handle_service_choice(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return

    service = await crud.get_service_by_button(message.text)
    if not service:
        return

    lang = await crud.get_user_lang(message.from_user.id)
    logging.info(f"🟢 SERVICE: user={message.from_user.id} chose='{service['id']}' lang={lang}")

    header = t("service_header", lang).format(
        emoji=service["emoji"],
        title=service["title"],
        short_desc=service["short_desc"] or ""
    )
    full_text = header + service["terms"] + t("terms_footer", lang)

    await message.answer(full_text, reply_markup=get_agree_keyboard_localized(service["id"], lang))
