"""
Добавление и точечная правка услуг.

Услуга живёт в двух языках: название, описание, условия и текст кнопки
заполняются отдельно для UA и RU. На любом шаге можно:
  • написать «=» — скопировать украинский вариант в русский;
  • /cancel — прервать мастер.
"""
import logging
import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.database import crud
from app.data.texts import (
    ADMIN_SERVICE_ADD_BUTTON_EXISTS_RU,
    ADMIN_SERVICE_ADD_BUTTON_LONG_RU,
    ADMIN_SERVICE_ADD_BUTTON_RU_RU,
    ADMIN_SERVICE_ADD_BUTTON_UA_RU,
    ADMIN_SERVICE_ADD_EMOJI_RU,
    ADMIN_SERVICE_ADD_EMPTY_RU,
    ADMIN_SERVICE_ADD_ID_EXISTS_RU,
    ADMIN_SERVICE_ADD_ID_INVALID_RU,
    ADMIN_SERVICE_ADD_ID_SHORT_RU,
    ADMIN_SERVICE_ADD_SHORT_RU_RU,
    ADMIN_SERVICE_ADD_SHORT_UA_RU,
    ADMIN_SERVICE_ADD_START_RU,
    ADMIN_SERVICE_ADD_TERMS_RU_RU,
    ADMIN_SERVICE_ADD_TERMS_UA_RU,
    ADMIN_SERVICE_ADD_TITLE_RU_RU,
    ADMIN_SERVICE_ADD_TITLE_UA_RU,
    ADMIN_SERVICE_CREATED_RU,
    ADMIN_SERVICE_EDIT_ASK_RU,
    ADMIN_SERVICE_EDIT_CHOOSE_FIELD_RU,
    ADMIN_SERVICE_EDIT_CHOOSE_LANG_RU,
    ADMIN_SERVICE_EDIT_STATE_LOST_RU,
    ADMIN_SERVICE_UPDATED_RU,
)
from app.keyboards.inline import admin_panel_kb, service_edit_field_kb, service_edit_lang_kb
from app.states.admin_states import AddService, EditService
from app.utils.callbacks import cb_args
from app.utils.telegram import answer_callback, cb_send, edit_or_send
from app.utils.text import BUTTON_LIMIT, esc, first_emoji

router = Router()
router.message.filter(F.chat.id == settings.ADMIN_CHAT_ID)

COPY_MARK = "="  # «скопировать как в украинской версии»

# ID услуги уходит в callback_data («svc:view:<id>»), поэтому двоеточия и
# прочие символы в нём недопустимы — иначе кнопки панели начинают путать услуги.
SERVICE_ID_RE = re.compile(r"^[a-z0-9_]{3,32}$")

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


def _validate_button_label(label: str) -> str | None:
    """Возвращает текст ошибки или None, если подпись кнопки допустима."""
    if not label:
        return ADMIN_SERVICE_ADD_EMPTY_RU
    if len(label) > BUTTON_LIMIT:
        # Telegram отбраковывает всю клавиатуру с кнопкой длиннее 64 символов
        return ADMIN_SERVICE_ADD_BUTTON_LONG_RU
    return None


# ═══════════════════════════════════════
#  Мастер добавления услуги
# ═══════════════════════════════════════

@router.callback_query(F.data == "svc:add")
async def start_add(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AddService.id)
    await cb_send(cb, ADMIN_SERVICE_ADD_START_RU + "\n<i>Или /cancel для отмены</i>")
    await answer_callback(cb)


@router.message(StateFilter(AddService.id), F.text)
async def add_id(message: Message, state: FSMContext):
    sid = message.text.strip().lower().replace(" ", "_")
    if len(sid) < 3:
        await message.answer(ADMIN_SERVICE_ADD_ID_SHORT_RU)
        return
    if not SERVICE_ID_RE.match(sid):
        await message.answer(ADMIN_SERVICE_ADD_ID_INVALID_RU)
        return
    if await crud.get_service_by_id(sid):
        await message.answer(ADMIN_SERVICE_ADD_ID_EXISTS_RU)
        return
    await state.update_data(id=sid)
    await state.set_state(AddService.emoji)
    await message.answer(ADMIN_SERVICE_ADD_EMOJI_RU)


@router.message(StateFilter(AddService.emoji), F.text)
async def add_emoji(message: Message, state: FSMContext):
    # Первый эмодзи целиком: прежнее text[:2] резало составные эмодзи
    # (👨‍👩‍👦, 🇺🇦, 🛡️) пополам, и в интерфейсе появлялись «квадратики».
    emoji = first_emoji(message.text) or message.text.strip()[:8]
    await state.update_data(emoji=emoji)
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
                    ADMIN_SERVICE_ADD_BUTTON_UA_RU.format(example=esc(data.get("title_ua", "")[:20]))
                )
            else:
                await message.answer(prompt)

        router.message.register(_step, StateFilter(state_obj), F.text)


_register_wizard_steps()


@router.message(StateFilter(AddService.button_ua), F.text)
async def add_button_ua(message: Message, state: FSMContext):
    label = (message.text or "").strip()
    error = _validate_button_label(label)
    if error:
        await message.answer(error)
        return
    if await crud.is_button_label_taken(label):
        await message.answer(ADMIN_SERVICE_ADD_BUTTON_EXISTS_RU)
        return
    await state.update_data(button_label_ua=label)
    await state.set_state(AddService.button_ru)
    await message.answer(
        ADMIN_SERVICE_ADD_BUTTON_RU_RU.format(example_ru=esc(label))
        + "\n<i>Или /cancel для отмены</i>"
    )


@router.message(StateFilter(AddService.button_ru), F.text)
async def add_button_ru(message: Message, state: FSMContext):
    label = (message.text or "").strip()
    data = await state.get_data()

    if label == COPY_MARK:
        label = data.get("button_label_ua", "")
    error = _validate_button_label(label)
    if error:
        await message.answer(error)
        return
    if await crud.is_button_label_taken(label):
        await message.answer(ADMIN_SERVICE_ADD_BUTTON_EXISTS_RU)
        return

    data["button_label_ru"] = label
    try:
        await crud.create_service(data)
    except Exception as e:
        logging.exception("Ошибка создания услуги")
        await message.answer(f"❌ Ошибка: <code>{esc(e)}</code>")
        await state.clear()
        return

    await message.answer(
        ADMIN_SERVICE_CREATED_RU.format(
            title=esc(data.get("title_ua") or data["id"]),
            title_ua=esc(data.get("title_ua")), title_ru=esc(data.get("title_ru")),
            button_ua=esc(data.get("button_label_ua")), button_ru=esc(data.get("button_label_ru")),
        ),
        reply_markup=admin_panel_kb(),
    )
    await state.clear()


# ═══════════════════════════════════════
#  Точечная правка услуги
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("svc:edit:"))
async def edit_choose_lang(cb: CallbackQuery, state: FSMContext):
    (sid,) = cb_args(cb.data, "svc:edit:")
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await answer_callback(cb, "Не найдено")
        return
    await state.clear()
    await edit_or_send(
        cb,
        ADMIN_SERVICE_EDIT_CHOOSE_LANG_RU.format(title=esc(svc["title_ua"])),
        reply_markup=service_edit_lang_kb(sid),
    )
    await answer_callback(cb)


@router.callback_query(F.data.startswith("svc:editlang:"))
async def edit_choose_field(cb: CallbackQuery):
    sid, lang = cb_args(cb.data, "svc:editlang:", tail=1)
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await answer_callback(cb, "Не найдено")
        return
    await edit_or_send(
        cb,
        ADMIN_SERVICE_EDIT_CHOOSE_FIELD_RU.format(title=esc(svc["title_ua"]), lang=esc(lang).upper()),
        reply_markup=service_edit_field_kb(sid, lang),
    )
    await answer_callback(cb)


@router.callback_query(F.data.startswith("svc:editfield:"))
async def edit_field_ask(cb: CallbackQuery, state: FSMContext):
    sid, lang, field = cb_args(cb.data, "svc:editfield:", tail=2)
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await answer_callback(cb, "Не найдено")
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
    await cb_send(
        cb,
        ADMIN_SERVICE_EDIT_ASK_RU.format(
            field=esc(field_name), lang=esc(lang).upper(), current=esc(current)
        )
    )
    await answer_callback(cb)


@router.message(StateFilter(EditService.value), F.text)
async def edit_field_save(message: Message, state: FSMContext):
    data = await state.get_data()
    value = (message.text or "").strip()
    if not value:
        await message.answer(ADMIN_SERVICE_ADD_EMPTY_RU)
        return

    sid, field, lang = data.get("edit_sid"), data.get("edit_field"), data.get("edit_lang")
    if not sid or not field or not lang:
        # Состояние могло сброситься (рестарт бота, /cancel) — раньше здесь
        # падал AttributeError на None.startswith().
        await state.clear()
        await message.answer(ADMIN_SERVICE_EDIT_STATE_LOST_RU)
        return

    if field.startswith("button_label"):
        error = _validate_button_label(value)
        if error:
            await message.answer(error)
            return
        if await crud.is_button_label_taken(value, exclude_id=sid):
            await message.answer(ADMIN_SERVICE_ADD_BUTTON_EXISTS_RU)
            return

    try:
        await crud.update_service_field(sid, field, value)
    except Exception as e:
        logging.exception("Ошибка обновления услуги")
        await message.answer(f"❌ Ошибка: <code>{esc(e)}</code>")
        await state.clear()
        return

    svc = await crud.get_service_by_id(sid)
    await message.answer(
        ADMIN_SERVICE_UPDATED_RU.format(
            field=esc(data.get("edit_field_name", field)),
            lang=esc(lang).upper(),
            title=esc(svc["title_ua"]) if svc else esc(sid),
        )
    )
    await state.clear()
