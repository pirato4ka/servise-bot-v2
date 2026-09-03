import logging
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from app.config import settings
from app.database import crud
from app.data.texts import ADMIN_INVOICE_MISMATCH_RU, ADMIN_INVOICE_PAID_RU, t
from app.services.cryptopay import CryptoInvoice, get_invoice_status
from app.utils.telegram import answer_callback, cb_reply
from app.utils.text import MESSAGE_LIMIT, esc, fit, format_amount

router = Router()


def _amounts_match(record, invoice) -> bool:
    try:
        if float(record["amount"]) != float(invoice.amount):
            return False
    except (TypeError, ValueError):
        pass
    if record["asset"] and invoice.asset:
        return record["asset"].upper() == invoice.asset.upper()
    return True


def _invoice_id_from_cb(data: str) -> Optional[int]:
    """'checkpay:4242' -> 4242. Битые данные -> None (раньше падал ValueError)."""
    try:
        return int(data.split(":", 1)[1])
    except (IndexError, ValueError):
        return None


async def apply_invoice_payment(
    bot: Bot, crypto_id: int, notify: bool = True, invoice: Optional[CryptoInvoice] = None
) -> Optional[dict]:
    """
    Проверяет счёт в CryptoBot и, если он оплачен, фиксирует оплату:
    обновляет invoices/tickets и уведомляет пользователя и админ-чат.
    Возвращает запись счёта, если оплата была зафиксирована (иначе None).

    ``invoice`` можно передать готовым — фоновый вотчер получает статусы
    пачкой и не должен запрашивать каждый счёт второй раз.
    """
    if invoice is None:
        invoice = await get_invoice_status(crypto_id)
    if not invoice or invoice.status != "paid":
        return None

    record = await crud.get_invoice_by_crypto_id(crypto_id)
    if not record:
        logging.warning(f"PAYMENT: invoice {crypto_id} оплачен, но не найден в БД")
        return None

    # mark_invoice_paid атомарен: повторный вызов (вотчер + кнопка одновременно)
    # вернёт None, и уведомления не задублируются.
    paid = await crud.mark_invoice_paid(crypto_id)
    if not paid:
        return None

    mismatch = None if _amounts_match(record, invoice) else ADMIN_INVOICE_MISMATCH_RU.format(
        expected_amount=esc(record["amount"]), expected_asset=esc(record["asset"]),
        paid_amount=esc(invoice.amount), paid_asset=esc(invoice.asset),
    )
    if mismatch:
        logging.warning(f"PAYMENT: несовпадение суммы по инвойсу {crypto_id}")

    if notify:
        lang = await crud.get_user_lang(record["user_id"])
        try:
            await bot.send_message(
                chat_id=record["user_id"],
                text=fit(
                    t("invoice_paid_user", lang), MESSAGE_LIMIT,
                    amount=format_amount(invoice.amount), asset=esc(invoice.asset),
                ),
            )
        except Exception as e:
            logging.warning(f"PAYMENT: не удалось уведомить пользователя {record['user_id']}: {e}")

        ticket = await crud.get_ticket_by_id(record["ticket_id"]) if record["ticket_id"] else None
        service = await crud.get_service_by_id(ticket["service_id"]) if ticket and ticket["service_id"] else None
        user_row = await crud.get_user(record["user_id"])

        admin_text = fit(ADMIN_INVOICE_PAID_RU, MESSAGE_LIMIT, **{
            "user_id": record["user_id"],
            "username": esc("@" + user_row["username"]) if user_row and user_row["username"] else "—",
            "service_title": esc((service["title_ru"] or service["title_ua"]) if service else "—"),
            "amount": format_amount(invoice.amount),
            "asset": esc(invoice.asset),
            "crypto_id": esc(crypto_id),
        })
        if mismatch:
            admin_text += "\n" + mismatch
        try:
            await bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=admin_text,
                reply_to_message_id=ticket["admin_message_id"] if ticket else None,
            )
        except Exception as e:
            logging.warning(f"PAYMENT: не удалось уведомить админ-чат: {e}")

    return record


# Проверка оплаты пользователем
@router.callback_query(F.data.startswith("checkpay:"))
async def user_check_pay(cb: CallbackQuery):
    crypto_id = _invoice_id_from_cb(cb.data)
    lang = await crud.get_user_lang(cb.from_user.id)

    if crypto_id is None:
        await answer_callback(cb, t("invoice_not_found", lang), show_alert=True)
        return

    record = await crud.get_invoice_by_crypto_id(crypto_id)
    # Счёт должен принадлежать тому, кто нажал кнопку
    if not record or record["user_id"] != cb.from_user.id:
        await answer_callback(cb, t("invoice_not_found", lang), show_alert=True)
        return

    invoice = await get_invoice_status(crypto_id)
    if not invoice:
        await answer_callback(cb, t("invoice_not_found", lang), show_alert=True)
        return

    if invoice.status != "paid":
        await answer_callback(cb, t("invoice_not_paid", lang), show_alert=True)
        return

    applied = await apply_invoice_payment(cb.bot, crypto_id)
    if applied is None:
        # Оплату уже зафиксировал фоновый вотчер — уведомление пользователь
        # получил тогда же, второй раз дублировать его не нужно.
        logging.info(f"PAYMENT: счёт {crypto_id} уже был проведён ранее")
    await answer_callback(cb, t("invoice_paid_check", lang), show_alert=True)


# Проверка оплаты админом (всегда русский)
@router.callback_query(F.data.startswith("admin_check:"))
async def admin_check_pay(cb: CallbackQuery):
    crypto_id = _invoice_id_from_cb(cb.data)
    if crypto_id is None or not await crud.is_admin(cb.from_user.id):
        await answer_callback(cb, "Недоступно", show_alert=True)
        return

    invoice = await get_invoice_status(crypto_id)
    if not invoice:
        await answer_callback(cb, "Инвойс не найден", show_alert=True)
        return

    amount = f"{format_amount(invoice.amount)} {invoice.asset}"
    if invoice.status == "paid":
        await apply_invoice_payment(cb.bot, crypto_id)
        await cb_reply(
            cb, f"✅ <b>Оплачен!</b>\n\nСумма: {esc(amount)}\nID: <code>{esc(crypto_id)}</code>"
        )
        await answer_callback(cb, "Оплачен")
    elif invoice.status == "active":
        # Текст алерта/ответа показывается как есть, HTML там не нужен
        await answer_callback(cb, f"⏳ Еще не оплачен. Статус: {invoice.status}\nСумма: {amount}")
    else:
        await answer_callback(cb, f"Статус: {invoice.status}")
