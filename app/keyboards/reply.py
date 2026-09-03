from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.database import crud
from app.data.texts import t
from app.utils.text import BUTTON_LIMIT


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


def service_button_label(service: dict, lang: str = "ua") -> str:
    """
    Текст кнопки услуги, ужатый под лимит Telegram (64 символа).

    Без этого одна слишком длинная метка роняла всю клавиатуру:
    Telegram отвечал 400 «BUTTON_TEXT_INVALID», и пользователь оставался
    вообще без меню услуг. Обрезка не ломает поиск услуги —
    ``crud.get_service_by_button`` умеет матчить и укороченный вариант.
    """
    localized = crud.localize_service(service, lang) or {}
    label = localized.get("button_label") or localized.get("title") or service.get("id") or ""
    return str(label).strip()[:BUTTON_LIMIT]


async def get_services_keyboard(lang: str = "ua") -> ReplyKeyboardMarkup:
    """Кнопки услуг — на языке, который выбрал пользователь."""
    services = await crud.get_services(active_only=True)

    buttons: list[list[KeyboardButton]] = []
    row: list[KeyboardButton] = []
    seen: set[str] = set()

    for service in services:
        label = service_button_label(service, lang)
        # Пустые и дублирующиеся подписи Telegram тоже отбраковывает всей клавиатурой
        if not label or label in seen:
            continue
        seen.add(label)
        row.append(KeyboardButton(text=label))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
