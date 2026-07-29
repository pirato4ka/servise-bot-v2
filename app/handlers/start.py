import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from app.config import settings
from app.database import crud
from app.database.db import get_db
from app.data.texts import t
from app.keyboards.inline import get_lang_keyboard
from app.keyboards.reply import get_services_keyboard


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""

    # Source tracking
    source = "direct"
    if message.text and len(message.text.split()) > 1:
        source = message.text.split()[1]

    # Upsert user
    await crud.upsert_user(user_id, username, full_name, source)

    # Проверяем — выбран ли язык?
    db = await get_db()
    async with db.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)) as cur:
        row = await cur.fetchone()
    await db.close()

    lang = row["lang"] if row and row["lang"] else None

    if lang:
        # Язык уже выбран — показываем welcome
        await _send_welcome(message, lang, source)
    else:
        # Первый запуск — просим выбрать язык
        await message.answer(
            "🌐 Оберіть мову / Выберите язык:",
            reply_markup=get_lang_keyboard()
        )


@router.callback_query(F.data.startswith("lang:"))
async def choose_lang(cb: CallbackQuery):
    lang = cb.data.split(":")[1]
    user_id = cb.from_user.id

    await crud.set_user_lang(user_id, lang)
    logging.info(f"🌐 LANG: user={user_id} set lang={lang}")

    # Убираем клавиатуру выбора
    try:
        await cb.message.delete()
    except:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except:
            pass

    # Source
    db = await get_db()
    async with db.execute("SELECT source FROM users WHERE user_id=?", (user_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    source = row["source"] if row else "direct"

    await _send_welcome(cb.message, lang, source)
    await cb.answer()


@router.message(Command("lang"))
async def cmd_lang(message: Message):
    """Смена языка в любой момент"""
    await message.answer(
        "🌐 Оберіть мову / Выберите язык:",
        reply_markup=get_lang_keyboard()
    )


async def _send_welcome(message: Message, lang: str, source: str):
    if source and source != "direct":
        source_line = t("source_channel", lang).format(source=source)
    else:
        source_line = t("source_direct", lang)

    welcome_text = t("welcome", lang).format(source_line=source_line)
    kb = await get_services_keyboard()
    await message.answer(welcome_text, reply_markup=kb)
