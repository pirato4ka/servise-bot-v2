from aiogram.fsm.state import StatesGroup, State


class AddService(StatesGroup):
    id = State()
    emoji = State()
    title = State()
    button_label = State()
    short_desc = State()
    terms = State()


class EditService(StatesGroup):
    field_choice = State()
    new_value = State()


class ConfirmPayment(StatesGroup):
    waiting_price = State()
    waiting_decline_reason = State()


class Broadcast(StatesGroup):
    waiting_interval = State()
    waiting_text = State()
    waiting_photo = State()
    waiting_confirm = State()
