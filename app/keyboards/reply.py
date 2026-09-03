from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from app.data.texts import t
from app.database import crud


def get_cancel_keyboard(lang: str = "ua") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_cancel", lang))]],
        resize_keyboard=True
    )


def get_recipient_keyboard(lang: str = "ua") -> ReplyKeyboardMarkup:
    """Шаг 3/3 — кому требуется услуга + кнопка отмены."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("btn_for_me", lang)),
                KeyboardButton(text=t("btn_for_relative", lang)),
                KeyboardButton(text=t("btn_for_friend", lang)),
            ],
            [KeyboardButton(text=t("btn_cancel", lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def get_services_keyboard(lang: str = "ua") -> ReplyKeyboardMarkup:
    """Кнопки услуг — на языке, который выбрал пользователь."""
    services = await crud.get_services(active_only=True)
    if not services:
        return ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)

    buttons = []
    row = []
    for i, s in enumerate(services):
        localized = crud.localize_service(s, lang)
        row.append(KeyboardButton(text=localized["button_label"]))
        if len(row) == 2 or i == len(services) - 1:
            buttons.append(row)
            row = []

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
