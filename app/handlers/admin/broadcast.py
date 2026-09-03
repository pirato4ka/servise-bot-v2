import asyncio
import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter

from app.config import settings
from app.database import crud
from app.states.admin_states import Broadcast

router = Router()

# Хранилище активных задач рассылки (id рассылки -> asyncio.Task)
active_tasks: dict[int, asyncio.Task] = {}


async def is_admin_user(user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    if chat_id == settings.ADMIN_CHAT_ID:
        return True
    return await crud.is_admin(user_id)


# ═══════════════════════════════════════
#  /cancel — отмена в любом состоянии рассылки
# ═══════════════════════════════════════

@router.message(Command("cancel"), StateFilter(Broadcast))
async def broadcast_cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.reply("❌ Настройка рассылки отменена.")


@router.message(Command("cancel"), F.chat.id == settings.ADMIN_CHAT_ID)
async def broadcast_cancel_fallback(message: Message, state: FSMContext):
    """Если /cancel не перехватил никто другой — просто чистим состояние (только админ-чат)."""
    if await state.get_state() is None:
        return
    await state.clear()
    await message.reply("❌ Действие отменено.")


# ═══════════════════════════════════════
#  Кнопка «📢 Рассылка»
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin:broadcast")
async def broadcast_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()

    if not await is_admin_user(cb.from_user.id, cb.message.chat.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.clear()
    await state.set_state(Broadcast.waiting_interval)

    await cb.message.answer(
        "📢 <b>Настройка рассылки</b>\n\n"
        "Укажите <b>периодичность</b> в часах:\n"
        "• <code>24</code> — раз в сутки\n"
        "• <code>12</code> — каждые 12 часов\n"
        "• <code>168</code> — раз в неделю\n"
        "• <code>0.5</code> — каждые 30 минут (тест)\n\n"
        "<i>Или /cancel для отмены</i>"
    )
    logging.info(f"📢 Broadcast setup started by user {cb.from_user.id}")


# ═══════════════════════════════════════
#  Шаг 1: Периодичность
# ═══════════════════════════════════════

@router.message(StateFilter(Broadcast.waiting_interval), F.text)
async def broadcast_interval(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return

    text = message.text.strip().replace(",", ".")
    try:
        hours = float(text)
        if hours <= 0:
            raise ValueError("Число должно быть больше 0")
    except (ValueError, TypeError):
        await message.reply("❌ Введите корректное число больше 0.\nПример: <code>24</code> или <code>0.5</code>")
        return

    await state.update_data(interval_hours=hours)
    await state.set_state(Broadcast.waiting_text)
    await message.reply(
        f"✅ Периодичность: каждые <b>{hours}</b> ч.\n\n"
        "Теперь отправьте <b>текст рассылки</b> (поддерживается HTML):\n\n"
        "<i>Или /cancel для отмены</i>"
    )


# ═══════════════════════════════════════
#  Шаг 2: Текст рассылки
# ═══════════════════════════════════════

@router.message(StateFilter(Broadcast.waiting_text))
async def broadcast_text(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return

    if message.text and message.text.startswith("/"):
        await message.reply("❌ Неизвестная команда.\nОтправьте текст рассылки или /cancel для отмены.")
        return

    text = message.text or message.caption or ""
    if not text.strip():
        await message.reply("❌ Сообщение не содержит текста.\nОтправьте текст или фото с подписью.")
        return

    await state.update_data(broadcast_text=text)
    await state.set_state(Broadcast.waiting_photo)
    await message.reply(
        "✅ Текст принят.\n\nХотите добавить <b>фото</b> к рассылке?\n"
        "• Отправьте фото\n• Или напишите /skip чтобы пропустить"
    )


# ═══════════════════════════════════════
#  Шаг 3: Фото (или пропуск)
# ═══════════════════════════════════════

@router.message(StateFilter(Broadcast.waiting_photo), Command("skip"))
async def broadcast_skip_photo(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return
    await state.update_data(photo_file_id=None)
    await state.set_state(Broadcast.waiting_confirm)
    await send_preview(message, state)


@router.message(StateFilter(Broadcast.waiting_photo), F.photo)
async def broadcast_photo(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await state.set_state(Broadcast.waiting_confirm)
    await send_preview(message, state)


@router.message(StateFilter(Broadcast.waiting_photo), F.text)
async def broadcast_photo_text_fallback(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return
    if message.text.startswith("/"):
        await message.reply("❌ Неизвестная команда.\nОтправьте фото, напишите /skip или /cancel.")
        return
    await state.update_data(photo_file_id=None)
    await state.set_state(Broadcast.waiting_confirm)
    await send_preview(message, state)


# ═══════════════════════════════════════
#  Превью + Подтверждение
# ═══════════════════════════════════════

async def send_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    interval = data.get("interval_hours")
    text = data.get("broadcast_text")
    photo_id = data.get("photo_file_id")

    if interval is None or not text:
        await message.reply("❌ Ошибка: данные рассылки потеряны. Начните заново через меню.")
        await state.clear()
        return

    total = len(await crud.get_broadcast_targets())

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Запустить", callback_data="broadcast:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel"),
        ]
    ])

    preview_header = (
        f"📢 <b>Превью рассылки</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"⏰ Периодичность: каждые <b>{interval}</b> ч.\n"
        f"👥 Получателей: <b>{total}</b>\n"
        f"📷 Фото: {'Да' if photo_id else 'Нет'}\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"<b>Текст сообщения:</b>\n"
        f"{text}\n\n"
        f"<i>Подтвердите запуск:</i>"
    )

    try:
        if photo_id:
            await message.bot.send_photo(
                chat_id=message.chat.id, photo=photo_id, caption=preview_header,
                reply_markup=kb, parse_mode="HTML",
            )
        else:
            await message.reply(preview_header, reply_markup=kb)
    except Exception as exc:
        logging.error(f"Preview send error: {exc}")
        try:
            await message.reply(
                f"📢 Превью\n⏰ {interval}ч. | 👥 {total} чел. | 📷 {'Да' if photo_id else 'Нет'}\n\n{text}",
                reply_markup=kb,
            )
        except Exception as exc2:
            logging.error(f"Preview fallback error: {exc2}")


@router.callback_query(F.data == "broadcast:confirm")
async def broadcast_confirm(cb: CallbackQuery, state: FSMContext):
    if not await is_admin_user(cb.from_user.id, cb.message.chat.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return

    await cb.answer("🚀 Запускаю...")

    data = await state.get_data()
    if not data.get("broadcast_text") or data.get("interval_hours") is None:
        await cb.message.answer("❌ Данные рассылки устарели или потеряны. Начните настройку заново.")
        await state.clear()
        return

    interval = data["interval_hours"]
    text = data["broadcast_text"]
    photo_id = data.get("photo_file_id")

    broadcast_id = await crud.create_broadcast(cb.from_user.id, interval, text, photo_id)
    if not broadcast_id:
        await cb.message.answer("❌ Ошибка сохранения в базу данных. Попробуйте снова.")
        await state.clear()
        return

    await state.clear()

    task = asyncio.create_task(broadcast_loop(cb.bot, broadcast_id, interval_hours=interval, initial_delay=0))
    active_tasks[broadcast_id] = task

    await cb.message.answer(
        f"🚀 <b>Рассылка #{broadcast_id} запущена!</b>\n\n"
        f"⏰ Каждые {interval} ч.\n"
        f"📨 Первая отправка через {interval} ч.\n\n"
        f"🛑 Остановить: /stopbroadcast {broadcast_id}\n"
        f"📋 Список всех: /broadcasts"
    )
    logging.info(f"📢 Broadcast #{broadcast_id} started by {cb.from_user.id}: interval={interval}h")


@router.callback_query(F.data == "broadcast:cancel")
async def broadcast_cancel_cb(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Отменено")
    await state.clear()
    await cb.message.answer("❌ Настройка рассылки отменена.")


# ═══════════════════════════════════════
#  Отправка
# ═══════════════════════════════════════

async def _send_one(bot: Bot, uid: int, text: str, photo_id: str | None) -> str:
    """Отправляет одно сообщение, аккуратно переживая лимиты Telegram."""
    for attempt in range(3):
        try:
            if photo_id:
                await bot.send_photo(chat_id=uid, photo=photo_id, caption=text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            return "sent"
        except TelegramRetryAfter as e:
            await asyncio.sleep(float(getattr(e, "retry_after", 1)) + 0.5)
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "not found" in err or "chat not found" in err:
                return "blocked"
            if attempt == 2:
                return "failed"
            await asyncio.sleep(1)
        except Exception:
            if attempt == 2:
                return "failed"
            await asyncio.sleep(1)
    return "failed"


async def run_broadcast(bot: Bot, broadcast_id: int, current_text: str, current_photo: str | None) -> dict:
    users = await crud.get_broadcast_targets()
    sent = failed = blocked = 0

    for user in users:
        result = await _send_one(bot, user["user_id"], current_text, current_photo)
        if result == "sent":
            sent += 1
        elif result == "blocked":
            blocked += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)  # антиспам Telegram

    await crud.touch_broadcast(broadcast_id)
    logging.info(f"📢 Broadcast #{broadcast_id} done: sent={sent}, failed={failed}, blocked={blocked}")

    try:
        await bot.send_message(
            chat_id=settings.ADMIN_CHAT_ID,
            text=(
                f"📢 <b>Рассылка #{broadcast_id} выполнена</b>\n"
                f"✅ Отправлено: {sent}\n"
                f"🚫 Заблокировали бота: {blocked}\n"
                f"❌ Других ошибок: {failed}"
            ),
        )
    except Exception as exc:
        logging.error(f"📢 Admin notification failed: {exc}")

    return {"sent": sent, "failed": failed, "blocked": blocked}


async def broadcast_loop(
    bot: Bot,
    broadcast_id: int,
    interval_hours: float,
    text: str = "",
    photo_id: str | None = None,
    initial_delay: float | None = None,
):
    """
    initial_delay=None → ждать полный интервал;
    0 → отправить сразу (первый запуск);
    N → подождать N секунд (восстановление после рестарта).
    """
    delay = interval_hours * 3600 if initial_delay is None else initial_delay
    logging.info(f"📢 Broadcast #{broadcast_id} loop started: every {interval_hours}h, first delay={delay}s")

    try:
        while True:
            if delay > 0:
                await asyncio.sleep(delay)
            delay = interval_hours * 3600

            row = await crud.get_broadcast(broadcast_id)
            if not row or not row["is_active"]:
                logging.info(f"📢 Broadcast #{broadcast_id}: deactivated, stopping loop")
                break

            # Текст/фото берём актуальные из БД — можно менять на ходу
            current_text = row["text"] or text
            current_photo = row["photo_file_id"] if row["photo_file_id"] is not None else photo_id

            await run_broadcast(bot, broadcast_id, current_text, current_photo)

    except asyncio.CancelledError:
        logging.info(f"📢 Broadcast #{broadcast_id}: task cancelled")
        raise
    except Exception as exc:
        logging.error(f"📢 Broadcast #{broadcast_id} unexpected error: {exc}", exc_info=True)
        try:
            await bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=f"⚠️ Рассылка #{broadcast_id} упала с ошибкой:\n<code>{exc}</code>",
            )
        except Exception:
            pass
    finally:
        active_tasks.pop(broadcast_id, None)
        logging.info(f"📢 Broadcast #{broadcast_id}: task finished")


# ═══════════════════════════════════════
#  Команды управления
# ═══════════════════════════════════════

@router.message(Command("stopbroadcast"))
async def stop_broadcast(message: Message):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.reply("❌ Использование: <code>/stopbroadcast &lt;id&gt;</code>\nПример: <code>/stopbroadcast 3</code>")
        return

    bid = int(args[1])

    if bid in active_tasks:
        active_tasks[bid].cancel()
        try:
            await active_tasks[bid]
        except (asyncio.CancelledError, Exception):
            pass

    await crud.deactivate_broadcast(bid)
    active_tasks.pop(bid, None)

    await message.reply(f"🛑 Рассылка #{bid} остановлена.")
    logging.info(f"📢 Broadcast #{bid} stopped by {message.from_user.id}")


@router.message(Command("broadcasts"))
async def list_broadcasts(message: Message):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return

    rows = await crud.get_recent_broadcasts()
    if not rows:
        await message.reply("📋 Рассылок пока нет.")
        return

    lines = ["📢 <b>Последние рассылки:</b>\n"]
    for r in rows:
        status = "🟢 Активна" if r["is_active"] else "🔴 Остановлена"
        in_memory = "⚡ в памяти" if r["id"] in active_tasks else "💤 нет задачи"
        text_preview = r["text"][:60] + ("..." if len(r["text"]) > 60 else "")
        lines.append(
            f"<b>#{r['id']}</b> | {status} | {in_memory}\n"
            f"⏰ Каждые {r['interval_hours']}ч.\n"
            f"📝 {text_preview}\n"
        )

    await message.reply("\n".join(lines))


# ═══════════════════════════════════════
#  Загрузка при старте бота
# ═══════════════════════════════════════

def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


async def load_active_broadcasts(bot: Bot) -> int:
    """
    Восстанавливает активные рассылки из БД при старте бота.
    Учитывает last_sent_at: если интервал уже истёк — отправляем сразу,
    иначе дожимаем только остаток.
    """
    rows = await crud.get_active_broadcasts()
    if not rows:
        logging.info("📢 No active broadcasts to restore")
        return 0

    restored = 0
    for row in rows:
        bid = row["id"]
        if bid in active_tasks:
            continue

        interval_seconds = float(row["interval_hours"]) * 3600
        last_sent = _parse_dt(row.get("last_sent_at")) or _parse_dt(row.get("created_at"))
        elapsed = (datetime.now() - last_sent).total_seconds() if last_sent else interval_seconds
        initial_delay = max(0.0, interval_seconds - elapsed)

        task = asyncio.create_task(
            broadcast_loop(
                bot,
                bid,
                interval_hours=float(row["interval_hours"]),
                text=row["text"],
                photo_id=row["photo_file_id"],
                initial_delay=initial_delay,
            )
        )
        active_tasks[bid] = task
        restored += 1
        logging.info(f"📢 Restored broadcast #{bid}: every {row['interval_hours']}h, send in {initial_delay:.0f}s")

    logging.info(f"📢 Total broadcasts restored: {restored}")
    return restored


async def stop_all_broadcasts():
    """Остановка всех задач рассылки при завершении работы бота."""
    for bid, task in list(active_tasks.items()):
        task.cancel()
    for bid, task in list(active_tasks.items()):
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    active_tasks.clear()
