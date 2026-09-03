"""
Добавление и точечная правка услуг.

Услуга живёт в двух языках: название, описание, условия и текст кнопки
заполняются отдельно для UA и RU. На любом шаге можно:
  • написать «=» — скопировать украинский вариант в русский;
  • /cancel — прервать мастер.
"""
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from app.config import settings
from app.database import crud
from app.keyboards.inline import admin_panel_kb, service_edit_lang_kb, service_edit_field_kb
from app.data.texts import (
    ADMIN_SERVICE_ADD_START_RU, ADMIN_SERVICE_ADD_EMOJI_RU,
    ADMIN_SERVICE_ADD_TITLE_UA_RU, ADMIN_SERVICE_ADD_TITLE_RU_RU,
    ADMIN_SERVICE_ADD_SHORT_UA_RU, ADMIN_SERVICE_ADD_SHORT_RU_RU,
    ADMIN_SERVICE_ADD_TERMS_UA_RU, ADMIN_SERVICE_ADD_TERMS_RU_RU,
    ADMIN_SERVICE_ADD_BUTTON_UA_RU, ADMIN_SERVICE_ADD_BUTTON_RU_RU,
    ADMIN_SERVICE_ADD_ID_SHORT_RU, ADMIN_SERVICE_ADD_ID_EXISTS_RU,
    ADMIN_SERVICE_ADD_BUTTON_EXISTS_RU, ADMIN_SERVICE_ADD_EMPTY_RU,
    ADMIN_SERVICE_CREATED_RU, ADMIN_SERVICE_UPDATED_RU,
    ADMIN_SERVICE_EDIT_CHOOSE_LANG_RU, ADMIN_SERVICE_EDIT_CHOOSE_FIELD_RU,
    ADMIN_SERVICE_EDIT_ASK_RU,
)
from app.states.admin_states import AddService, EditService

router = Router()
router.message.filter(F.chat.id == settings.ADMIN_CHAT_ID)

COPY_MARK = "="  # «скопировать как в украинской версии»

FIELD_LABELS = {
    "title": "название",
    "short_desc": "краткое описание",
    "terms": "условия",
    "button_label": "текст кнопки",
    "emoji": "эмодзи",
}

# (текущее состояние, ключ данных, следующее состояние, вопрос СЛЕДУЮЩЕГО шага)
WIZARD_STEPS = (
    (AddService.title_ua, "title_ua", AddService.title_ru, ADMIN_SERVICE_ADD_TITLE_RU_RU),
    (AddService.title_ru, "title_ru", AddService.short_ua, ADMIN_SERVICE_ADD_SHORT_UA_RU),
    (AddService.short_ua, "short_desc_ua", AddService.short_ru, ADMIN_SERVICE_ADD_SHORT_RU_RU),
    (AddService.short_ru, "short_desc_ru", AddService.terms_ua, ADMIN_SERVICE_ADD_TERMS_UA_RU),
    (AddService.terms_ua, "terms_ua", AddService.terms_ru, ADMIN_SERVICE_ADD_TERMS_RU_RU),
    # следующий шаг — кнопка UA, у него свой вопрос с примером
    (AddService.terms_ru, "terms_ru", AddService.button_ua, None),
)


def _in_admin_chat(message: Message) -> bool:
    return message.chat.id == settings.ADMIN_CHAT_ID


# ═══════════════════════════════════════
#  Мастер добавления услуги
# ═══════════════════════════════════════

@router.callback_query(F.data == "svc:add")
async def start_add(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AddService.id)
    await cb.message.answer(ADMIN_SERVICE_ADD_START_RU + "\n<i>Или /cancel для отмены</i>")
    await cb.answer()


@router.message(StateFilter(AddService.id), F.text)
async def add_id(message: Message, state: FSMContext):
    sid = message.text.strip().lower().replace(" ", "_")
    if len(sid) < 3:
        await message.answer(ADMIN_SERVICE_ADD_ID_SHORT_RU)
        return
    if await crud.get_service_by_id(sid):
        await message.answer(ADMIN_SERVICE_ADD_ID_EXISTS_RU)
        return
    await state.update_data(id=sid)
    await state.set_state(AddService.emoji)
    await message.answer(ADMIN_SERVICE_ADD_EMOJI_RU)


@router.message(StateFilter(AddService.emoji), F.text)
async def add_emoji(message: Message, state: FSMContext):
    await state.update_data(emoji=message.text.strip()[:2])
    await state.set_state(AddService.title_ua)
    await message.answer(ADMIN_SERVICE_ADD_TITLE_UA_RU)


def _register_wizard_steps():
    """Создаёт обработчики для однотипных шагов UA -> RU."""
    for state_obj, data_key, next_state, next_prompt in WIZARD_STEPS:
        is_ru_step = data_key.endswith("_ru")

        async def _step(message: Message, state: FSMContext,
                        key=data_key, nxt=next_state, prompt=next_prompt, ru=is_ru_step):
            value = (message.text or "").strip()
            if not value:
                await message.answer(ADMIN_SERVICE_ADD_EMPTY_RU)
                return
            if ru and value == COPY_MARK:
                data = await state.get_data()
                value = data.get(key.replace("_ru", "_ua"), "")
                if not value:
                    await message.answer(ADMIN_SERVICE_ADD_EMPTY_RU)
                    return

            await state.update_data(**{key: value})
            await state.set_state(nxt)

            if prompt is None:  # следующий шаг — кнопка UA (нужен пример)
                data = await state.get_data()
                await message.answer(
                    ADMIN_SERVICE_ADD_BUTTON_UA_RU.format(example=data.get("title_ua", "")[:20])
                )
            else:
                await message.answer(prompt)

        router.message.register(_step, StateFilter(state_obj), F.text)


_register_wizard_steps()


@router.message(StateFilter(AddService.button_ua), F.text)
async def add_button_ua(message: Message, state: FSMContext):
    label = (message.text or "").strip()
    if not label:
        await message.answer(ADMIN_SERVICE_ADD_EMPTY_RU)
        return
    if await crud.is_button_label_taken(label):
        await message.answer(ADMIN_SERVICE_ADD_BUTTON_EXISTS_RU)
        return
    await state.update_data(button_label_ua=label)
    await state.set_state(AddService.button_ru)
    await message.answer(
        ADMIN_SERVICE_ADD_BUTTON_RU_RU.format(example_ru=label)
        + "\n<i>Или /cancel для отмены</i>"
    )


@router.message(StateFilter(AddService.button_ru), F.text)
async def add_button_ru(message: Message, state: FSMContext):
    label = (message.text or "").strip()
    data = await state.get_data()

    if not label:
        await message.answer(ADMIN_SERVICE_ADD_EMPTY_RU)
        return
    if label == COPY_MARK:
        label = data.get("button_label_ua", "")
        if not label:
            await message.answer(ADMIN_SERVICE_ADD_EMPTY_RU)
            return
    if await crud.is_button_label_taken(label):
        await message.answer(ADMIN_SERVICE_ADD_BUTTON_EXISTS_RU)
        return

    data["button_label_ru"] = label
    try:
        await crud.create_service(data)
    except Exception as e:
        logging.exception("Ошибка создания услуги")
        await message.answer(f"❌ Ошибка: {e}")
        await state.clear()
        return

    await message.answer(
        ADMIN_SERVICE_CREATED_RU.format(
            title=data.get("title_ua", data["id"]),
            title_ua=data.get("title_ua"), title_ru=data.get("title_ru"),
            button_ua=data.get("button_label_ua"), button_ru=data.get("button_label_ru"),
        ),
        reply_markup=admin_panel_kb(),
    )
    await state.clear()


# ═══════════════════════════════════════
#  Точечная правка услуги
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("svc:edit:"))
async def edit_choose_lang(cb: CallbackQuery, state: FSMContext):
    sid = cb.data.split(":")[2]
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await cb.answer("Не найдено")
        return
    await state.clear()
    await cb.message.edit_text(
        ADMIN_SERVICE_EDIT_CHOOSE_LANG_RU.format(title=svc["title_ua"]),
        reply_markup=service_edit_lang_kb(sid),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("svc:editlang:"))
async def edit_choose_field(cb: CallbackQuery):
    _, _, sid, lang = cb.data.split(":")
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await cb.answer("Не найдено")
        return
    await cb.message.edit_text(
        ADMIN_SERVICE_EDIT_CHOOSE_FIELD_RU.format(
            title=svc["title_ua"], lang=lang.upper()
        ),
        reply_markup=service_edit_field_kb(sid, lang),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("svc:editfield:"))
async def edit_field_ask(cb: CallbackQuery, state: FSMContext):
    _, _, sid, lang, field = cb.data.split(":")
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await cb.answer("Не найдено")
        return

    if field == "emoji":
        current = svc["emoji"] or "—"
        field_name, db_field = "эмодзи", "emoji"
    else:
        field_name = FIELD_LABELS.get(field, field)
        db_field = f"{field}_{lang}"
        current = svc[db_field] or "—"

    await state.clear()
    await state.update_data(edit_sid=sid, edit_field=db_field,
                            edit_lang=lang, edit_field_name=field_name)
    await state.set_state(EditService.value)
    await cb.message.answer(
        ADMIN_SERVICE_EDIT_ASK_RU.format(field=field_name, lang=lang.upper(), current=current)
    )
    await cb.answer()


@router.message(StateFilter(EditService.value), F.text)
async def edit_field_save(message: Message, state: FSMContext):
    data = await state.get_data()
    value = (message.text or "").strip()
    if not value:
        await message.answer(ADMIN_SERVICE_ADD_EMPTY_RU)
        return

    sid, field, lang = data.get("edit_sid"), data.get("edit_field"), data.get("edit_lang")
    if field.startswith("button_label") and await crud.is_button_label_taken(value, exclude_id=sid):
        await message.answer(ADMIN_SERVICE_ADD_BUTTON_EXISTS_RU)
        return

    try:
        await crud.update_service_field(sid, field, value)
    except Exception as e:
        logging.exception("Ошибка обновления услуги")
        await message.answer(f"❌ Ошибка: {e}")
        await state.clear()
        return

    svc = await crud.get_service_by_id(sid)
    await message.answer(
        ADMIN_SERVICE_UPDATED_RU.format(
            field=data.get("edit_field_name", field),
            lang=lang.upper(),
            title=svc["title_ua"] if svc else sid,
        )
    )
    await state.clear()
