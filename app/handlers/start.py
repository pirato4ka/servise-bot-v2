import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import crud
from app.data.texts import t
from app.keyboards.inline import get_lang_keyboard
from app.keyboards.reply import get_services_keyboard
from app.utils.text import esc

router = Router()

# Deep-link payload из t.me/bot?start=xxx Telegram ограничивает символами
# A-Z a-z 0-9 _ -, но команду можно набрать руками — поэтому чистим сами:
# значение уходит в HTML-шаблон приветствия и в поле «Источник» заявки.
_SOURCE_RE = re.compile(r"[^A-Za-z0-9_\-@.]")
SOURCE_MAX_LEN = 64


def parse_source(text: str | None) -> str:
    """'/start channel_x' -> 'channel_x'; без параметра -> 'direct'."""
    if not text:
        return "direct"
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return "direct"
    cleaned = _SOURCE_RE.sub("", parts[1].strip())[:SOURCE_MAX_LEN]
    return cleaned or "direct"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not message.from_user:  # пост из канала: from_user отсутствует
        return
    await state.clear()

    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""

    source = parse_source(message.text)

    await crud.upsert_user(user_id, username, full_name, source)

    if await crud.is_banned(user_id):
        lang = await crud.get_user_lang(user_id)
        await message.answer(t("banned_user", lang))
        return

    # Проверяем — выбран ли язык?
    user_row = await crud.get_user(user_id)
    lang = user_row["lang"] if user_row and user_row["lang"] else None

    if lang:
        # Язык уже выбран — показываем welcome
        await _send_welcome(message.bot, message.chat.id, lang, source)
    else:
        # Первый запуск — просим выбрать язык
        await message.answer(
            t("choose_lang", lang or "ua"),
            reply_markup=get_lang_keyboard()
        )


@router.callback_query(F.data.startswith("lang:"))
async def choose_lang(cb: CallbackQuery):
    lang = cb.data.split(":", 1)[1]
    if lang not in ("ua", "ru"):
        await cb.answer()
        return

    user_id = cb.from_user.id
    # Сообщение с кнопкой может быть уже недоступно (InaccessibleMessage):
    # у него нет .answer()/.delete(), поэтому работаем через chat.id и бота.
    chat_id = cb.message.chat.id if cb.message else user_id

    await cb.answer()

    # Строки в users может не быть (база пересоздана, кнопка на старом
    # сообщении) — без upsert язык сохранялся в никуда и выбор зацикливался.
    await crud.upsert_user(user_id, cb.from_user.username or "", cb.from_user.full_name or "")
    await crud.set_user_lang(user_id, lang)
    logging.info(f"🌐 LANG: user={user_id} set lang={lang}")

    # Убираем клавиатуру выбора
    try:
        await cb.message.delete()
    except Exception:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    user_row = await crud.get_user(user_id)
    source = user_row["source"] if user_row and user_row["source"] else "direct"

    await _send_welcome(cb.bot, chat_id, lang, source)


@router.message(Command("lang"))
async def cmd_lang(message: Message):
    """Смена языка в любой момент"""
    if not message.from_user:
        return
    await message.answer(
        t("choose_lang", await crud.get_user_lang(message.from_user.id)),
        reply_markup=get_lang_keyboard()
    )


@router.message(Command("cancel"), F.chat.type == "private")
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена анкеты в личке: текста про /cancel раньше не было обработчика."""
    if not message.from_user:
        return
    await state.clear()
    lang = await crud.get_user_lang(message.from_user.id)
    kb = await get_services_keyboard(lang)
    await message.answer(t("cancel_message", lang), reply_markup=kb)


async def _send_welcome(bot: Bot, chat_id: int, lang: str, source: str):
    if source and source != "direct":
        source_line = t("source_channel", lang).format(source=esc(source))
    else:
        source_line = t("source_direct", lang)

    welcome_text = t("welcome", lang).format(source_line=source_line)
    kb = await get_services_keyboard(lang)
    await bot.send_message(chat_id=chat_id, text=welcome_text, reply_markup=kb)
