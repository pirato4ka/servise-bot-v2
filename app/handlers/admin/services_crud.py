from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from app.states.admin_states import AddService
from app.database import crud
from app.keyboards.inline import admin_panel_kb

from app.data.texts import (
    ADMIN_SERVICE_ADD_START_RU, ADMIN_SERVICE_ADD_EMOJI_RU,
    ADMIN_SERVICE_ADD_TITLE_RU, ADMIN_SERVICE_ADD_BUTTON_RU,
    ADMIN_SERVICE_ADD_SHORT_RU, ADMIN_SERVICE_ADD_TERMS_RU,
    ADMIN_SERVICE_ADD_ID_SHORT_RU, ADMIN_SERVICE_ADD_ID_EXISTS_RU,
    ADMIN_SERVICE_CREATED_RU, ADMIN_SERVICE_UPDATED_RU
)

router = Router()

@router.callback_query(F.data == "svc:add")
async def start_add(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddService.id)
    await cb.message.answer(ADMIN_SERVICE_ADD_START_RU)
    await cb.answer()

@router.message(StateFilter(AddService.id), F.text)
async def add_id(message: Message, state: FSMContext):
    sid = message.text.strip().lower().replace(" ", "_")
    if len(sid) < 3:
        await message.answer(ADMIN_SERVICE_ADD_ID_SHORT_RU)
        return
    exists = await crud.get_service_by_id(sid)
    if exists:
        await message.answer(ADMIN_SERVICE_ADD_ID_EXISTS_RU)
        return
    await state.update_data(id=sid)
    await state.set_state(AddService.emoji)
    await message.answer(ADMIN_SERVICE_ADD_EMOJI_RU)

@router.message(StateFilter(AddService.emoji), F.text)
async def add_emoji(message: Message, state: FSMContext):
    await state.update_data(emoji=message.text.strip()[:2])
    await state.set_state(AddService.title)
    await message.answer(ADMIN_SERVICE_ADD_TITLE_RU)

@router.message(StateFilter(AddService.title), F.text)
async def add_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddService.button_label)
    await message.answer(ADMIN_SERVICE_ADD_BUTTON_RU.format(example=message.text.strip()[:20]))

@router.message(StateFilter(AddService.button_label), F.text)
async def add_button_label(message: Message, state: FSMContext):
    await state.update_data(button_label=message.text.strip())
    await state.set_state(AddService.short_desc)
    await message.answer(ADMIN_SERVICE_ADD_SHORT_RU)

@router.message(StateFilter(AddService.short_desc), F.text)
async def add_short(message: Message, state: FSMContext):
    await state.update_data(short_desc=message.text.strip())
    await state.set_state(AddService.terms)
    await message.answer(ADMIN_SERVICE_ADD_TERMS_RU)

@router.message(StateFilter(AddService.terms), F.text)
async def add_terms(message: Message, state: FSMContext):
    data = await state.get_data()
    # Если это редактирование существующей (edit_id в стейте)
    if "edit_id" in data:
        sid = data["edit_id"]
        svc = await crud.get_service_by_id(sid)
        if svc:
            new_data = {
                "emoji": svc["emoji"],
                "title": svc["title"],
                "button_label": svc["button_label"],
                "short_desc": svc["short_desc"],
                "terms": message.text
            }
            await crud.update_service(sid, new_data)
            await message.answer(ADMIN_SERVICE_UPDATED_RU.format(title=svc['title']), reply_markup=admin_panel_kb())
            await state.clear()
            return

    # Обычное создание
    data['terms'] = message.text
    try:
        await crud.create_service(data)
        await message.answer(ADMIN_SERVICE_CREATED_RU.format(title=data['title']), reply_markup=admin_panel_kb())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    await state.clear()

@router.callback_query(F.data.startswith("svc:edit:"))
async def edit_start(cb: CallbackQuery, state: FSMContext):
    sid = cb.data.split(":")[2]
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await cb.answer("Не найдено")
        return
    await state.update_data(edit_id=sid)
    await state.set_state(AddService.terms)
    await cb.message.answer(f"✏️ Редактирование {svc['title']}\n\nТекущие условия:\n{svc['terms']}\n\nВведи <b>НОВЫЕ условия</b>:")
    await cb.answer()
