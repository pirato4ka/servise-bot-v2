from aiogram.fsm.state import StatesGroup, State


class Questionnaire(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_recipient = State()  # шаг 3/3: Мне / Родному / Другу
