import logging
from dataclasses import replace

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.database import crud
from app.data.texts import (
    ADMIN_ASK_PRICE_RU,
    ADMIN_DECLINE_ASK_REASON_RU,
    ADMIN_INVOICE_CREATED_RU,
    ADMIN_INVOICE_CREATING_RU,
    ADMIN_INVOICE_ERROR_RU,
    ADMIN_PRICE_INVALID_RU,
    t,
)
from app.keyboards.inline import admin_check_invoice_kb, user_invoice_kb
from app.services.cryptopay import create_infinite_invoice
from app.states.admin_states import AddService, ConfirmPayment
from app.utils.telegram import answer_callback, cb_chat_id, cb_reply
from app.utils.text import MESSAGE_LIMIT, esc, fit, format_amount

router = Router()


def _service_title(service) -> str:
    """Название услуги для админ-чата: русское, иначе украинское."""
    if not service:
        return "—"
    return service["title_ru"] or service["title_ua"]


async def _build_user_display(user_id: int) -> str:
    row = await crud.get_user(user_id)
    if not row:
        return f"<code>{user_id}</code>"
    username = row["username"]
    full_name = esc(row["full_name"] or "—")
    if username:
        return f"<code>{user_id}</code> | @{esc(username)} | {full_name}"
    return f"<code>{user_id}</code> | {full_name}"


def parse_price(text: str):
    """'100 USDT' / '0,05 BTC' -> (100.0, 'USDT'). Иначе None."""
    parts = (text or "").strip().split()
    if len(parts) != 2:
        return None
    try:
        amount = float(parts[0].replace(",", "."))
        asset = parts[1].upper()
    except (TypeError, ValueError):
        return None
    if amount <= 0 or not asset.isalnum():
        return None
    return amount, asset


async def _is_ticket_admin(cb: CallbackQuery) -> bool:
    """Разрешаем нажимать кнопки заявки только из админ-чата либо админам из БД.

    Раньше проверялся только ``cb.message.chat.id == ADMIN_CHAT_ID``. Если
    Telegram отдал InaccessibleMessage (сообщение старше 48 ч или недоступное
    боту) — ``cb_chat_id`` уводил проверку в личку админа, и кнопки заявки
    любые отвечали «Недоступно».
    """
    if not cb.from_user:
        return False
    if cb_chat_id(cb) == settings.ADMIN_CHAT_ID:
        return True
    return await crud.is_admin(cb.from_user.id)


def _admin_chat_fsm_key(state: FSMContext):
    """Ключ FSM для ввода в админ-чате.

    Для обычного колбека из группы ``state.key.chat_id`` уже равен
    ``ADMIN_CHAT_ID``. Если же Telegram прислал InaccessibleMessage и aiogram
    ключ построил по ``from_user`` (личка), всё равно пишем состояние под
    админ-чатом: админ продолжает ввод именно там, где увидел кнопку.
    """
    return replace(state.key, chat_id=settings.ADMIN_CHAT_ID)


async def _set_admin_fsm(state: FSMContext, new_state, data: dict) -> None:
    """Сохраняет состояние/данные для админ-чата (обходя личку при InaccessibleMessage)."""
    key = _admin_chat_fsm_key(state)
    await state.storage.set_state(key, new_state)
    await state.storage.set_data(key, data)


async def _admin_ticket_cb_reply(cb: CallbackQuery, text: str, reply_markup=None) -> bool:
    """Отвечает на кнопку заявки в админ-чате.

    Если оригинальное сообщение кнопки ещё доступно — отвечаем в тот же тред.
    Если сообщение недоступно/удалено (InaccessibleMessage), не уводим ответ в
    личку: шлём новое сообщение прямо в админ-чат.
    """
    if cb.message and cb.message.chat.id == settings.ADMIN_CHAT_ID:
        return await cb_reply(cb, text, reply_markup=reply_markup)

    try:
        await cb.bot.send_message(
            chat_id=settings.ADMIN_CHAT_ID,
            text=text,
            reply_markup=reply_markup,
        )
        return True
    except Exception as e:  # noqa: BLE001 — ответ на кнопку не должен ронять обработчик
        logging.error(f"ADMIN_TICKET: не удалось ответить в админ-чат: {e}")
        return False


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
    logging.info(f"🔴 CONFIRM: data={cb.data} chat={cb.message.chat.id if cb.message else '?'}")

    if not await _is_ticket_admin(cb):
        await answer_callback(cb, "Недоступно", show_alert=True)
        return

    await answer_callback(cb)  # Убираем "часики" на кнопке

    try:
        admin_msg_id = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        await _admin_ticket_cb_reply(cb, "❌ Некорректные данные кнопки")
        return

    ticket = await crud.get_ticket_by_admin_msg(admin_msg_id)
    if not ticket:
        # Кнопка всегда несёт message_id заявки; поиск по id тикета здесь
        # приводил к подтверждению ЧУЖОЙ заявки с выставлением счета не тому
        # клиенту, поэтому fallback убран.
        logging.warning(f"CONFIRM: заявка по admin_message_id={admin_msg_id} не найдена")
        await _admin_ticket_cb_reply(cb, f"❌ Заявка {admin_msg_id} не найдена")
        return

    if ticket["status"] != "open":
        await _admin_ticket_cb_reply(cb, f"⚠️ Заявка уже обработана ({esc(ticket['status'])})")
        return

    # Сбрасываем предыдущее состояние (и текущего чата, и админ-чата)
    await state.clear()
    await _set_admin_fsm(state, ConfirmPayment.waiting_price, {
        "confirm_admin_msg_id": ticket["admin_message_id"],
        "confirm_ticket_id": ticket["id"],
        "confirm_user_id": ticket["user_id"],
        "confirm_service_id": ticket["service_id"],
        "action": "confirm",
    })

    await _admin_ticket_cb_reply(
        cb,
        ADMIN_ASK_PRICE_RU.format(user_id=ticket["user_id"]) + "\n<i>Или /cancel для отмены</i>"
    )


# ═══════════════════════════════════════
#  ❌ ОТКЛОНИТЬ (CallbackQuery - ВЫШЕ текстовых хендлеров!)
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("ticket:decline:"))
async def ticket_decline_start(cb: CallbackQuery, state: FSMContext):
    logging.info(f"🔴 DECLINE: data={cb.data} chat={cb.message.chat.id if cb.message else '?'}")

    if not await _is_ticket_admin(cb):
        await answer_callback(cb, "Недоступно", show_alert=True)
        return

    await answer_callback(cb)  # Убираем "часики"

    try:
        admin_msg_id = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        await _admin_ticket_cb_reply(cb, "❌ Некорректные данные кнопки")
        return

    ticket = await crud.get_ticket_by_admin_msg(admin_msg_id)
    if not ticket:
        await _admin_ticket_cb_reply(cb, "❌ Заявка не найдена")
        return

    if ticket["status"] != "open":
        await _admin_ticket_cb_reply(cb, f"⚠️ Заявка уже обработана ({esc(ticket['status'])})")
        return

    # Сбрасываем предыдущее состояние (и текущего чата, и админ-чата)
    await state.clear()
    await _set_admin_fsm(state, ConfirmPayment.waiting_decline_reason, {
        "confirm_admin_msg_id": admin_msg_id,
        "confirm_ticket_id": ticket["id"],
        "confirm_user_id": ticket["user_id"],
        "action": "decline",
    })

    await _admin_ticket_cb_reply(
        cb, ADMIN_DECLINE_ASK_REASON_RU + "\n<i>Или /cancel для отмены</i>"
    )


# ═══════════════════════════════════════
#  ВВОД ЦЕНЫ
# ═══════════════════════════════════════

@router.message(
    ConfirmPayment.waiting_price,  # Упрощенный синтаксис
    F.chat.id == settings.ADMIN_CHAT_ID,
    F.text,
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

    # Защита от повторного счета: за время ввода цены заявку могли
    # подтвердить ещё раз (другой админ или второй клик по кнопке).
    ticket = await crud.get_ticket_by_id(ticket_id)
    if not ticket or ticket["status"] != "open":
        await message.reply(f"⚠️ Заявка уже обработана ({esc(ticket['status']) if ticket else 'не найдена'})")
        await state.clear()
        return

    service = await crud.get_service_by_id(service_id)
    service_title = _service_title(service) if service else service_id

    await message.reply(
        ADMIN_INVOICE_CREATING_RU.format(amount=format_amount(amount), asset=esc(asset))
    )

    try:
        payload = f"{user_id}:{ticket_id}:{admin_msg_id}"
        description = f"Оплата {service_title} для {user_id}. Цена {format_amount(amount)} {asset}"
        invoice = await create_infinite_invoice(asset=asset, amount=amount, description=description, payload=payload)

        await crud.create_invoice_record(
            crypto_invoice_id=invoice.invoice_id, user_id=user_id,
            ticket_id=ticket_id, asset=asset, amount=str(amount),
            bot_url=invoice.bot_invoice_url, mini_url=invoice.mini_app_invoice_url, payload=payload
        )

        # Юзеру
        lang = await crud.get_user_lang(user_id)
        user_text = fit(
            t("invoice_created_user", lang), MESSAGE_LIMIT,
            service_title=esc(service_title), amount=format_amount(amount), asset=esc(asset),
        )
        kb_user = user_invoice_kb(invoice.bot_invoice_url, invoice.invoice_id, lang)
        await message.bot.send_message(chat_id=user_id, text=user_text, reply_markup=kb_user)

        # Админу
        user_display = await _build_user_display(user_id)
        admin_ok_text = fit(ADMIN_INVOICE_CREATED_RU, MESSAGE_LIMIT, **{
            "user_id": user_id, "user_display": user_display,
            "service_title": esc(service_title), "amount": format_amount(amount),
            "asset": esc(asset), "bot_url": esc(invoice.bot_invoice_url),
            "crypto_id": esc(invoice.invoice_id),
        })
        await message.reply(admin_ok_text, reply_markup=admin_check_invoice_kb(invoice.invoice_id))

        await crud.set_ticket_status(ticket_id, "invoice_sent")

    except Exception as e:
        logging.exception("Ошибка создания инвойса")
        await message.reply(fit(ADMIN_INVOICE_ERROR_RU, MESSAGE_LIMIT, e=esc(e)))

    await state.clear()


# ═══════════════════════════════════════
#  ПРИЧИНА ОТКЛОНЕНИЯ
# ═══════════════════════════════════════

@router.message(
    ConfirmPayment.waiting_decline_reason,
    F.chat.id == settings.ADMIN_CHAT_ID,
    F.text,
)
async def decline_reason_input(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("confirm_user_id")
    if not user_id:
        await state.clear()
        await message.reply("❌ Данные заявки потеряны. Нажми «Отклонить» ещё раз.")
        return

    reason = message.text.strip()

    try:
        lang = await crud.get_user_lang(user_id)
        # Причина пишется админом от руки и попадает внутрь <i>…</i>:
        # без экранирования «не прошли проверку & тест» теряли весь ответ.
        await message.bot.send_message(
            chat_id=user_id,
            text=fit(t("declined_user", lang), MESSAGE_LIMIT, reason=esc(reason)),
        )
        await message.reply(f"✅ Пользователю <code>{user_id}</code> отправлено отклонение.")

        await crud.set_ticket_status(data["confirm_ticket_id"], "declined")
    except Exception as e:
        logging.error(f"DECLINE: не удалось отправить отклонение: {e}")
        await message.reply(f"❌ Не удалось отправить: <code>{esc(e)}</code>")

    await state.clear()


# ═══════════════════════════════════════
#  /confirm (альтернатива)
# ═══════════════════════════════════════

@router.message(Command("confirm"), F.chat.id == settings.ADMIN_CHAT_ID)
async def confirm_command(message: Message, state: FSMContext):
    args = message.text.split()
    if len(args) < 3:
        await message.reply("/confirm <user_id> <сумма> <актив>\nПример: /confirm 7233200164 100 USDT")
        return

    ticket = None
    try:
        if len(args) == 3:
            amount = float(args[1].replace(",", "."))
            asset = args[2].upper()
            ticket = await crud.get_last_open_ticket()
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
            await message.reply(f"Тикет уже обработан ({esc(ticket['status'])})")
            return
    except (ValueError, IndexError) as e:
        await message.reply(f"Ошибка разбора аргументов: <code>{esc(e)}</code>")
        return
    except Exception as e:
        logging.exception("Ошибка /confirm")
        await message.reply(f"Ошибка: <code>{esc(e)}</code>")
        return

    service = await crud.get_service_by_id(ticket["service_id"])
    service_title = _service_title(service) if service else ticket["service_id"]

    await message.reply(ADMIN_INVOICE_CREATING_RU.format(amount=format_amount(amount), asset=esc(asset)))

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
        user_text = fit(
            t("invoice_created_user", lang), MESSAGE_LIMIT,
            service_title=esc(service_title), amount=format_amount(amount), asset=esc(asset),
        )
        await message.bot.send_message(
            chat_id=ticket["user_id"], text=user_text,
            reply_markup=user_invoice_kb(invoice.bot_invoice_url, invoice.invoice_id, lang),
        )

        user_display = await _build_user_display(ticket["user_id"])
        await message.reply(fit(ADMIN_INVOICE_CREATED_RU, MESSAGE_LIMIT, **{
            "user_id": ticket["user_id"], "user_display": user_display,
            "service_title": esc(service_title), "amount": format_amount(amount),
            "asset": esc(asset), "bot_url": esc(invoice.bot_invoice_url),
            "crypto_id": esc(invoice.invoice_id),
        }), reply_markup=admin_check_invoice_kb(invoice.invoice_id))

        await crud.set_ticket_status(ticket["id"], "invoice_sent")
    except Exception as e:
        logging.exception("Ошибка создания инвойса")
        await message.reply(fit(ADMIN_INVOICE_ERROR_RU, MESSAGE_LIMIT, e=esc(e)))

    await state.clear()
