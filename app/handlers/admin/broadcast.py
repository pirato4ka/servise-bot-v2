import asyncio
import logging
import time

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter

from app.config import settings
from app.database import crud
from app.database.db import get_db
from app.states.admin_states import Broadcast

router = Router()

# ═══════════════════════════════════════
#  Хранилище активных задач рассылки
# ═══════════════════════════════════════

active_tasks: dict[int, asyncio.Task] = {}


# ═══════════════════════════════════════
#  Вспомогательная проверка прав
# ═══════════════════════════════════════

async def is_admin_user(user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    if chat_id == settings.ADMIN_CHAT_ID:
        return True
    return await crud.is_admin(user_id)


# ═══════════════════════════════════════
#  /cancel — отмена в любом состоянии
# ═══════════════════════════════════════

@router.message(
    Command("cancel"),
    StateFilter(Broadcast)
)
async def broadcast_cancel_cmd(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        return
    await state.clear()
    await message.reply("❌ Настройка рассылки отменена.")


# ═══════════════════════════════════════
#  Кнопка "📢 Рассылка"
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin:broadcast")
async def broadcast_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()

    # Проверка прав
    if not await is_admin_user(cb.from_user.id, cb.message.chat.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return

    # Очищаем предыдущие данные FSM
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

@router.message(
    StateFilter(Broadcast.waiting_interval),
    F.text
)
async def broadcast_interval(message: Message, state: FSMContext):
    # Проверка прав
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return

    text = message.text.strip().replace(",", ".")
    try:
        hours = float(text)
        if hours <= 0:
            raise ValueError("Число должно быть больше 0")
    except (ValueError, TypeError):
        await message.reply(
            "❌ Введите корректное число больше 0.\n"
            "Пример: <code>24</code> или <code>0.5</code>"
        )
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

@router.message(
    StateFilter(Broadcast.waiting_text)
)
async def broadcast_text(message: Message, state: FSMContext):
    # Проверка прав
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return

    # Если пришла команда — не обрабатываем как текст
    if message.text and message.text.startswith("/"):
        await message.reply(
            "❌ Неизвестная команда.\n"
            "Отправьте текст рассылки или /cancel для отмены."
        )
        return

    text = message.text or message.caption or ""
    if not text.strip():
        await message.reply(
            "❌ Сообщение не содержит текста.\n"
            "Отправьте текст или фото с подписью."
        )
        return

    await state.update_data(broadcast_text=text)
    await state.set_state(Broadcast.waiting_photo)
    await message.reply(
        "✅ Текст принят.\n\n"
        "Хотите добавить <b>фото</b> к рассылке?\n"
        "• Отправьте фото\n"
        "• Или напишите /skip чтобы пропустить"
    )


# ═══════════════════════════════════════
#  Шаг 3: Фото (или пропуск)
# ═══════════════════════════════════════

@router.message(
    StateFilter(Broadcast.waiting_photo),
    Command("skip")
)
async def broadcast_skip_photo(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return

    await state.update_data(photo_file_id=None)
    await state.set_state(Broadcast.waiting_confirm)
    await send_preview(message, state)


@router.message(
    StateFilter(Broadcast.waiting_photo),
    F.photo
)
async def broadcast_photo(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return

    photo_file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=photo_file_id)
    await state.set_state(Broadcast.waiting_confirm)
    await send_preview(message, state)


@router.message(
    StateFilter(Broadcast.waiting_photo),
    F.text
)
async def broadcast_photo_text_fallback(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return

    # Команды (кроме /skip и /cancel уже обработаны выше)
    if message.text and message.text.startswith("/"):
        await message.reply(
            "❌ Неизвестная команда.\n"
            "Отправьте фото, напишите /skip или /cancel."
        )
        return

    # Любой текст — считаем что фото не нужно
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

    # Валидация данных
    if interval is None or not text:
        await message.reply(
            "❌ Ошибка: данные рассылки потеряны. Начните заново через меню."
        )
        await state.clear()
        return

    total = await crud.get_users_count()

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
                chat_id=message.chat.id,
                photo=photo_id,
                caption=preview_header,
                reply_markup=kb,
                parse_mode="HTML"
            )
        else:
            await message.reply(preview_header, reply_markup=kb)
    except Exception as exc:
        logging.error(f"Preview send error: {exc}")
        # Fallback без форматирования
        try:
            await message.reply(
                f"📢 Превью\n⏰ {interval}ч. | 👥 {total} чел. | 📷 {'Да' if photo_id else 'Нет'}\n\n{text}",
                reply_markup=kb
            )
        except Exception as exc2:
            logging.error(f"Preview fallback error: {exc2}")


@router.callback_query(F.data == "broadcast:confirm")
async def broadcast_confirm(cb: CallbackQuery, state: FSMContext):
    # Проверка прав
    if not await is_admin_user(cb.from_user.id, cb.message.chat.id):
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return

    await cb.answer("🚀 Запускаю...")

    data = await state.get_data()

    # Валидация — данные могли протухнуть
    if not data.get("broadcast_text") or data.get("interval_hours") is None:
        await cb.message.answer(
            "❌ Данные рассылки устарели или потеряны.\n"
            "Пожалуйста, начните настройку заново."
        )
        await state.clear()
        return

    interval = data["interval_hours"]
    text = data["broadcast_text"]
    photo_id = data.get("photo_file_id")

    # Сохраняем в БД
    broadcast_id = None
    db = await get_db()
    try:
        cur = await db.execute(
            "INSERT INTO broadcasts (admin_id, interval_hours, text, photo_file_id, is_active) "
            "VALUES (?, ?, ?, ?, 1)",
            (cb.from_user.id, interval, text, photo_id)
        )
        broadcast_id = cur.lastrowid
        await db.commit()
    except Exception as exc:
        logging.error(f"Broadcast DB insert error: {exc}")
        await cb.message.answer("❌ Ошибка сохранения в базу данных. Попробуйте снова.")
        await state.clear()
        return
    finally:
        await db.close()

    # Очищаем FSM ДО запуска задачи
    await state.clear()

    # Запускаем фоновую задачу
    task = asyncio.create_task(
        broadcast_loop(cb.bot, broadcast_id, interval, text, photo_id)
    )
    active_tasks[broadcast_id] = task

    await cb.message.answer(
        f"🚀 <b>Рассылка #{broadcast_id} запущена!</b>\n\n"
        f"⏰ Каждые {interval} ч.\n"
        f"📨 Первая отправка через {interval} ч.\n\n"
        f"🛑 Остановить: /stopbroadcast {broadcast_id}\n"
        f"📋 Список всех: /broadcasts"
    )
    logging.info(
        f"📢 Broadcast #{broadcast_id} started by {cb.from_user.id}: "
        f"interval={interval}h, photo={'yes' if photo_id else 'no'}"
    )


@router.callback_query(F.data == "broadcast:cancel")
async def broadcast_cancel_cb(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Отменено")
    await state.clear()
    await cb.message.answer("❌ Настройка рассылки отменена.")


# ═══════════════════════════════════════
#  Фоновая задача рассылки
# ═══════════════════════════════════════

async def broadcast_loop(
    bot: Bot,
    broadcast_id: int,
    interval_hours: float,
    text: str,
    photo_id: str | None,
    skip_first_sleep: bool = False  # True при восстановлении если пора слать
):
    logging.info(
        f"📢 Broadcast #{broadcast_id} loop started: "
        f"every {interval_hours}h, skip_first_sleep={skip_first_sleep}"
    )

    try:
        while True:
            # Ждём интервал (кроме случая принудительного пропуска)
            if not skip_first_sleep:
                await asyncio.sleep(interval_hours * 3600)
            skip_first_sleep = False  # Сбрасываем флаг после первого цикла

            # Проверяем активность в БД
            db = await get_db()
            try:
                async with db.execute(
                    "SELECT is_active FROM broadcasts WHERE id = ?",
                    (broadcast_id,)
                ) as cur:
                    row = await cur.fetchone()
            finally:
                await db.close()

            if not row or not row["is_active"]:
                logging.info(f"📢 Broadcast #{broadcast_id}: deactivated, stopping loop")
                break

            # Получаем актуальный текст и фото из БД (на случай обновления)
            db = await get_db()
            try:
                async with db.execute(
                    "SELECT text, photo_file_id FROM broadcasts WHERE id = ?",
                    (broadcast_id,)
                ) as cur:
                    broadcast_row = await cur.fetchone()
            finally:
                await db.close()

            if broadcast_row:
                current_text = broadcast_row["text"]
                current_photo = broadcast_row["photo_file_id"]
            else:
                current_text = text
                current_photo = photo_id

            # Получаем пользователей
            users = await crud.get_all_users(limit=10000)

            sent = 0
            failed = 0
            blocked = 0

            for user in users:
                uid = user["user_id"]

                # Пропускаем забаненных
                if user.get("is_banned"):
                    continue

                try:
                    if current_photo:
                        await bot.send_photo(
                            chat_id=uid,
                            photo=current_photo,
                            caption=current_text,
                            parse_mode="HTML"
                        )
                    else:
                        await bot.send_message(
                            chat_id=uid,
                            text=current_text,
                            parse_mode="HTML"
                        )
                    sent += 1
                except Exception as exc:
                    err_str = str(exc).lower()
                    if "blocked" in err_str or "deactivated" in err_str or "not found" in err_str:
                        blocked += 1
                    else:
                        failed += 1
                        logging.warning(f"📢 Broadcast #{broadcast_id} failed for {uid}: {exc}")

                # Задержка между сообщениями (антиспам Telegram)
                await asyncio.sleep(0.05)

            logging.info(
                f"📢 Broadcast #{broadcast_id} done: "
                f"sent={sent}, failed={failed}, blocked={blocked}"
            )

            # Уведомляем админа
            try:
                await bot.send_message(
                    chat_id=settings.ADMIN_CHAT_ID,
                    text=(
                        f"📢 <b>Рассылка #{broadcast_id} выполнена</b>\n"
                        f"✅ Отправлено: {sent}\n"
                        f"🚫 Заблокировали бота: {blocked}\n"
                        f"❌ Других ошибок: {failed}"
                    )
                )
            except Exception as exc:
                logging.error(f"📢 Admin notification failed: {exc}")

    except asyncio.CancelledError:
        logging.info(f"📢 Broadcast #{broadcast_id}: task cancelled")
        raise
    except Exception as exc:
        logging.error(f"📢 Broadcast #{broadcast_id} unexpected error: {exc}", exc_info=True)
        # Уведомляем админа об ошибке
        try:
            await bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=f"⚠️ Рассылка #{broadcast_id} упала с ошибкой:\n<code>{exc}</code>"
            )
        except Exception:
            pass
    finally:
        # Убираем задачу из словаря при завершении
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
        await message.reply(
            "❌ Использование: <code>/stopbroadcast &lt;id&gt;</code>\n"
            "Пример: <code>/stopbroadcast 3</code>"
        )
        return

    bid = int(args[1])

    # Отменяем задачу если есть
    if bid in active_tasks:
        active_tasks[bid].cancel()
        # active_tasks.pop удалится в finally блоке broadcast_loop
        await asyncio.sleep(0.1)  # Даём время на cancellation

    # Деактивируем в БД в любом случае
    db = await get_db()
    try:
        await db.execute(
            "UPDATE broadcasts SET is_active = 0 WHERE id = ?",
            (bid,)
        )
        await db.commit()
    finally:
        await db.close()

    # Убираем из словаря на случай если loop уже завершился
    active_tasks.pop(bid, None)

    await message.reply(f"🛑 Рассылка #{bid} остановлена.")
    logging.info(f"📢 Broadcast #{bid} stopped by {message.from_user.id}")


@router.message(Command("broadcasts"))
async def list_broadcasts(message: Message):
    if not await is_admin_user(message.from_user.id, message.chat.id):
        return

    db = await get_db()
    try:
        async with db.execute(
            "SELECT * FROM broadcasts ORDER BY id DESC LIMIT 10"
        ) as cur:
            rows = await cur.fetchall()
    finally:
        await db.close()

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

async def load_active_broadcasts(bot: Bot):
    """
    Восстанавливает активные рассылки из БД при старте бота.
    Проверяет время последней отправки и решает — слать сразу или ждать.
    """
    db = await get_db()
    try:
        async with db.execute(
            "SELECT * FROM broadcasts WHERE is_active = 1"
        ) as cur:
            rows = await cur.fetchall()
    finally:
        await db.close()

    if not rows:
        logging.info("📢 No active broadcasts to restore")
        return

    restored = 0
    for row in rows:
        bid = row["id"]

        if bid in active_tasks:
            logging.info(f"📢 Broadcast #{bid} already in memory, skipping")
            continue

        task = asyncio.create_task(
            broadcast_loop(
                bot,
                bid,
                row["interval_hours"],
                row["text"],
                row["photo_file_id"],
                skip_first_sleep=False  # После рестарта всегда ждём полный интервал
            )
        )
        active_tasks[bid] = task
        restored += 1
        logging.info(
            f"📢 Restored broadcast #{bid}: "
            f"every {row['interval_hours']}h"
        )

    logging.info(f"📢 Total broadcasts restored: {restored}")