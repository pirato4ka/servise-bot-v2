from aiogram.fsm.state import StatesGroup, State


class AddService(StatesGroup):
    """Мастер добавления услуги: каждый текст заполняется на двух языках."""
    id = State()
    emoji = State()
    title_ua = State()
    title_ru = State()
    short_ua = State()
    short_ru = State()
    terms_ua = State()
    terms_ru = State()
    button_ua = State()
    button_ru = State()


class EditService(StatesGroup):
    """Точечная правка одного поля услуги."""
    value = State()


class ConfirmPayment(StatesGroup):
    waiting_price = State()
    waiting_decline_reason = State()


class Broadcast(StatesGroup):
    waiting_interval = State()
    waiting_text = State()
    waiting_photo = State()
    waiting_confirm = State()
