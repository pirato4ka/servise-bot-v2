import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter

from app.config import settings
from app.database import crud
from app.database.db import get_db
from app.states.admin_states import ConfirmPayment, AddService
from app.services.cryptopay import create_infinite_invoice
from app.keyboards.inline import user_invoice_kb, admin_check_invoice_kb
from app.data.texts import (
    t, ADMIN_ASK_PRICE_RU, ADMIN_PRICE_INVALID_RU, ADMIN_INVOICE_CREATING_RU,
    ADMIN_INVOICE_CREATED_RU, ADMIN_INVOICE_ERROR_RU, ADMIN_DECLINE_ASK_REASON_RU
)

router = Router()


def _service_title(service) -> str:
    """Название услуги для админ-чата: русское, иначе украинское."""
    if not service:
        return "—"
    return service["title_ru"] or service["title_ua"]


async def _build_user_display(user_id: int) -> str:
    db = await get_db()
    async with db.execute("SELECT username, full_name FROM users WHERE user_id=?", (user_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        return f"<code>{user_id}</code>"
    username = row["username"]
    full_name = row["full_name"] or "—"
    if username:
        return f"<code>{user_id}</code> | @{username} | {full_name}"
    return f"<code>{user_id}</code> | {full_name}"


def parse_price(text: str):
    parts = text.strip().split()
    if len(parts) != 2:
        return None
    try:
        amount = float(parts[0].replace(",", "."))
        asset = parts[1].upper()
        if amount <= 0:
            return None
        return amount, asset
    except:
        return None


# ═══════════════════════════════════════
#  /cancel — сброс FSM состояния
# ═══════════════════════════════════════

@router.message(Command("cancel"), StateFilter(ConfirmPayment, AddService))
async def admin_cancel(message: Message, state: FSMContext):
    """Отмена только в своих состояниях — иначе /cancel перехватывал бы рассылку."""
    await state.clear()
    await message.reply("❌ Действие отменено. Можете обрабатывать любую заявку.")


# ═══════════════════════════════════════
#  ✅ ПОДТВЕРДИТЬ (CallbackQuery - ВЫШЕ текстовых хендлеров!)
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("ticket:confirm:"))
async def ticket_confirm_start(cb: CallbackQuery, state: FSMContext):
    logging.info(f"🔴 CONFIRM: data={cb.data} chat={cb.message.chat.id}")
    
    if cb.message.chat.id != settings.ADMIN_CHAT_ID:
        await cb.answer("Недоступно", show_alert=True)
        return

    await cb.answer()  # Убираем "часики" на кнопке

    try:
        admin_msg_id = int(cb.data.split(":")[2])

        ticket = await crud.get_ticket_by_admin_msg(admin_msg_id)
        if not ticket:
            ticket = await crud.get_ticket_by_id(admin_msg_id)
        if not ticket:
            await cb.message.reply(f"❌ Тикет {admin_msg_id} не найден")
            return

        if ticket["status"] != "open":
            await cb.message.reply(f"⚠️ Заявка уже обработана ({ticket['status']})")
            return

        # Сбрасываем предыдущее состояние
        await state.clear()

        await state.set_state(ConfirmPayment.waiting_price)
        await state.update_data(
            confirm_admin_msg_id=ticket["admin_message_id"],
            confirm_ticket_id=ticket["id"],
            confirm_user_id=ticket["user_id"],
            confirm_service_id=ticket["service_id"],
            action="confirm"
        )

        await cb.message.reply(
            ADMIN_ASK_PRICE_RU.format(user_id=ticket["user_id"])
            + "\n<i>Или /cancel для отмены</i>"
        )

    except Exception as e:
        logging.exception("Ошибка в обработчике подтверждения")
        await cb.message.reply(f"❌ Ошибка: {e}")


# ═══════════════════════════════════════
#  ❌ ОТКЛОНИТЬ (CallbackQuery - ВЫШЕ текстовых хендлеров!)
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("ticket:decline:"))
async def ticket_decline_start(cb: CallbackQuery, state: FSMContext):
    logging.info(f"🔴 DECLINE: data={cb.data} chat={cb.message.chat.id}")
    
    if cb.message.chat.id != settings.ADMIN_CHAT_ID:
        await cb.answer("Недоступно", show_alert=True)
        return

    await cb.answer()  # Убираем "часики"

    try:
        admin_msg_id = int(cb.data.split(":")[2])

        ticket = await crud.get_ticket_by_admin_msg(admin_msg_id)
        if not ticket:
            await cb.message.reply("❌ Тикет не найден")
            return

        if ticket["status"] != "open":
            await cb.message.reply(f"⚠️ Заявка уже обработана ({ticket['status']})")
            return

        # Сбрасываем предыдущее состояние
        await state.clear()

        await state.set_state(ConfirmPayment.waiting_decline_reason)
        await state.update_data(
            confirm_admin_msg_id=admin_msg_id,
            confirm_ticket_id=ticket["id"],
            confirm_user_id=ticket["user_id"],
            action="decline"
        )

        await cb.message.reply(
            ADMIN_DECLINE_ASK_REASON_RU
            + "\n<i>Или /cancel для отмены</i>"
        )

    except Exception as e:
        logging.exception("Ошибка в обработчике подтверждения")
        await cb.message.reply(f"❌ Ошибка: {e}")


# ═══════════════════════════════════════
#  ВВОД ЦЕНЫ
# ═══════════════════════════════════════

@router.message(
    ConfirmPayment.waiting_price,  # Упрощенный синтаксис
    F.chat.id == settings.ADMIN_CHAT_ID,
    F.text,
    ~F.reply_to_message
)
async def price_input(message: Message, state: FSMContext):
    data = await state.get_data()
    
    # Дополнительная проверка
    if data.get("action") != "confirm":
        return

    parsed = parse_price(message.text)
    if not parsed:
        await message.reply(ADMIN_PRICE_INVALID_RU)
        return

    amount, asset = parsed
    user_id = data["confirm_user_id"]
    ticket_id = data["confirm_ticket_id"]
    service_id = data["confirm_service_id"]
    admin_msg_id = data["confirm_admin_msg_id"]

    service = await crud.get_service_by_id(service_id)
    service_title = _service_title(service) if service else service_id

    await message.reply(ADMIN_INVOICE_CREATING_RU.format(amount=amount, asset=asset))

    try:
        payload = f"{user_id}:{ticket_id}:{admin_msg_id}"
        description = f"Оплата {service_title} для {user_id}. Цена {amount} {asset}"
        invoice = await create_infinite_invoice(asset=asset, amount=amount, description=description, payload=payload)

        await crud.create_invoice_record(
            crypto_invoice_id=invoice.invoice_id, user_id=user_id,
            ticket_id=ticket_id, asset=asset, amount=str(amount),
            bot_url=invoice.bot_invoice_url, mini_url=invoice.mini_app_invoice_url, payload=payload
        )

        # Юзеру
        lang = await crud.get_user_lang(user_id)
        user_text = t("invoice_created_user", lang).format(service_title=service_title, amount=amount, asset=asset)
        kb_user = user_invoice_kb(invoice.bot_invoice_url, invoice.invoice_id, lang)
        await message.bot.send_message(chat_id=user_id, text=user_text, reply_markup=kb_user)

        # Админу
        user_display = await _build_user_display(user_id)
        admin_ok_text = ADMIN_INVOICE_CREATED_RU.format(
            user_id=user_id, user_display=user_display,
            service_title=service_title, amount=amount, asset=asset,
            bot_url=invoice.bot_invoice_url, crypto_id=invoice.invoice_id
        )
        await message.reply(admin_ok_text, reply_markup=admin_check_invoice_kb(invoice.invoice_id))

        await crud.set_ticket_status(ticket_id, "invoice_sent")

    except Exception as e:
        logging.exception("Ошибка создания инвойса")
        await message.reply(ADMIN_INVOICE_ERROR_RU.format(e=str(e)[:1000]))

    await state.clear()


# ═══════════════════════════════════════
#  ПРИЧИНА ОТКЛОНЕНИЯ
# ═══════════════════════════════════════

@router.message(
    ConfirmPayment.waiting_decline_reason,
    F.chat.id == settings.ADMIN_CHAT_ID,
    F.text,
    ~F.reply_to_message
)
async def decline_reason_input(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data["confirm_user_id"]
    reason = message.text.strip()

    try:
        lang = await crud.get_user_lang(user_id)
        await message.bot.send_message(chat_id=user_id, text=t("declined_user", lang).format(reason=reason))
        await message.reply(f"✅ Пользователю <code>{user_id}</code> отправлено отклонение.")

        await crud.set_ticket_status(data["confirm_ticket_id"], "declined")
    except Exception as e:
        await message.reply(f"❌ Не удалось отправить: {e}")

    await state.clear()


# ═══════════════════════════════════════
#  /confirm (альтернатива)
# ═══════════════════════════════════════

@router.message(Command("confirm"), F.chat.id == settings.ADMIN_CHAT_ID)
async def confirm_command(message: Message, state: FSMContext):
    # Остальной код без изменений...
    args = message.text.split()
    if len(args) < 3:
        await message.reply("/confirm <user_id> <сумма> <актив>\nПример: /confirm 7233200164 100 USDT")
        return

    try:
        if len(args) == 3:
            amount = float(args[1].replace(",", "."))
            asset = args[2].upper()
            db = await get_db()
            async with db.execute("SELECT * FROM tickets WHERE status='open' ORDER BY id DESC LIMIT 1") as cur:
                ticket = await cur.fetchone()
            await db.close()
        else:
            first = int(args[1])
            amount = float(args[2].replace(",", "."))
            asset = args[3].upper()
            ticket = await crud.get_last_ticket_by_user(first)
            if not ticket:
                ticket = await crud.get_ticket_by_admin_msg(first)
            if not ticket:
                ticket = await crud.get_ticket_by_id(first)

        if not ticket:
            await message.reply("Тикет не найден")
            return
        if ticket["status"] != "open":
            await message.reply(f"Тикет уже обработан ({ticket['status']})")
            return
    except Exception as e:
        await message.reply(f"Ошибка: {e}")
        return

    service = await crud.get_service_by_id(ticket["service_id"])
    service_title = _service_title(service) if service else ticket["service_id"]

    await message.reply(ADMIN_INVOICE_CREATING_RU.format(amount=amount, asset=asset))

    try:
        payload = f"{ticket['user_id']}:{ticket['id']}:{ticket['admin_message_id']}"
        invoice = await create_infinite_invoice(
            asset=asset, amount=amount,
            description=f"Оплата {service_title}", payload=payload
        )

        await crud.create_invoice_record(
            crypto_invoice_id=invoice.invoice_id, user_id=ticket["user_id"],
            ticket_id=ticket["id"], asset=asset, amount=str(amount),
            bot_url=invoice.bot_invoice_url, mini_url=invoice.mini_app_invoice_url, payload=payload
        )

        lang = await crud.get_user_lang(ticket["user_id"])
        user_text = t("invoice_created_user", lang).format(service_title=service_title, amount=amount, asset=asset)
        await message.bot.send_message(
            chat_id=ticket["user_id"], text=user_text,
            reply_markup=user_invoice_kb(invoice.bot_invoice_url, invoice.invoice_id,
                                         await crud.get_user_lang(ticket["user_id"])),
        )

        user_display = await _build_user_display(ticket["user_id"])
        await message.reply(ADMIN_INVOICE_CREATED_RU.format(
            user_id=ticket["user_id"], user_display=user_display,
            service_title=service_title, amount=amount, asset=asset,
            bot_url=invoice.bot_invoice_url, crypto_id=invoice.invoice_id
        ), reply_markup=admin_check_invoice_kb(invoice.invoice_id))

        await crud.set_ticket_status(ticket["id"], "invoice_sent")
    except Exception as e:
        logging.exception("Ошибка создания инвойса")
        await message.reply(ADMIN_INVOICE_ERROR_RU.format(e=str(e)[:1000]))

    await state.clear()