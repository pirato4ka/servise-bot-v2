from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from app.data.texts import t
from app.database import crud


def get_cancel_keyboard(lang: str = "ua") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("btn_cancel", lang))]],
        resize_keyboard=True
    )


async def get_services_keyboard() -> ReplyKeyboardMarkup:
    services = await crud.get_services(active_only=True)
    if not services:
        return ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)

    buttons = []
    row = []
    for i, s in enumerate(services):
        row.append(KeyboardButton(text=s["button_label"]))
        if len(row) == 2 or i == len(services) - 1:
            buttons.append(row)
            row = []

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
