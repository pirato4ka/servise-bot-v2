import logging
from typing import Optional

from aiogram import Bot, Router, F
from aiogram.types import CallbackQuery

from app.config import settings
from app.database import crud
from app.data.texts import t, ADMIN_INVOICE_PAID_RU, ADMIN_INVOICE_MISMATCH_RU
from app.services.cryptopay import get_invoice_status

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


async def apply_invoice_payment(bot: Bot, crypto_id: int, notify: bool = True) -> Optional[dict]:
    """
    Проверяет счёт в CryptoBot и, если он оплачен, фиксирует оплату:
    обновляет invoices/tickets и уведомляет пользователя и админ-чат.
    Возвращает запись счёта, если оплата была зафиксирована (иначе None).
    """
    invoice = await get_invoice_status(crypto_id)
    if not invoice or invoice.status != "paid":
        return None

    record = await crud.get_invoice_by_crypto_id(crypto_id)
    if not record:
        logging.warning(f"PAYMENT: invoice {crypto_id} оплачен, но не найден в БД")
        return None

    paid = await crud.mark_invoice_paid(crypto_id)
    if not paid:  # уже фиксировали раньше
        return None

    mismatch = None if _amounts_match(record, invoice) else ADMIN_INVOICE_MISMATCH_RU.format(
        expected_amount=record["amount"], expected_asset=record["asset"],
        paid_amount=invoice.amount, paid_asset=invoice.asset,
    )
    if mismatch:
        logging.warning(f"PAYMENT: несовпадение суммы по инвойсу {crypto_id}")

    if notify:
        lang = await crud.get_user_lang(record["user_id"])
        try:
            await bot.send_message(
                chat_id=record["user_id"],
                text=t("invoice_paid_user", lang).format(amount=invoice.amount, asset=invoice.asset),
            )
        except Exception as e:
            logging.warning(f"PAYMENT: не удалось уведомить пользователя {record['user_id']}: {e}")

        ticket = await crud.get_ticket_by_id(record["ticket_id"]) if record["ticket_id"] else None
        service = await crud.get_service_by_id(ticket["service_id"]) if ticket and ticket["service_id"] else None
        user_row = await crud.get_user(record["user_id"])

        admin_text = ADMIN_INVOICE_PAID_RU.format(
            user_id=record["user_id"],
            username=("@" + user_row["username"]) if user_row and user_row["username"] else "—",
            service_title=service["title"] if service else "—",
            amount=invoice.amount,
            asset=invoice.asset,
            crypto_id=crypto_id,
        )
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
    crypto_id = int(cb.data.split(":")[1])
    lang = await crud.get_user_lang(cb.from_user.id)

    record = await crud.get_invoice_by_crypto_id(crypto_id)
    # Счёт должен принадлежать тому, кто нажал кнопку
    if not record or record["user_id"] != cb.from_user.id:
        await cb.answer(t("invoice_not_found", lang), show_alert=True)
        return

    invoice = await get_invoice_status(crypto_id)
    if not invoice:
        await cb.answer(t("invoice_not_found", lang), show_alert=True)
        return

    if invoice.status == "paid":
        await apply_invoice_payment(cb.bot, crypto_id)
        await cb.message.answer(
            t("invoice_paid_user", lang).format(amount=invoice.amount, asset=invoice.asset)
        )
        await cb.answer(t("invoice_paid_check", lang), show_alert=True)
    else:
        await cb.answer(t("invoice_not_paid", lang), show_alert=True)


# Проверка оплаты админом (всегда русский)
@router.callback_query(F.data.startswith("admin_check:"))
async def admin_check_pay(cb: CallbackQuery):
    crypto_id = int(cb.data.split(":")[1])
    invoice = await get_invoice_status(crypto_id)
    if not invoice:
        await cb.answer("Инвойс не найден", show_alert=True)
        return

    if invoice.status == "paid":
        await apply_invoice_payment(cb.bot, crypto_id)
        await cb.message.reply(
            f"✅ <b>Оплачен!</b>\n\nСумма: {invoice.amount} {invoice.asset}\nID: {crypto_id}"
        )
        await cb.answer("Оплачен")
    elif invoice.status == "active":
        await cb.answer(f"⏳ Еще не оплачен. Статус: {invoice.status}\nСумма: {invoice.amount} {invoice.asset}")
    else:
        await cb.answer(f"Статус: {invoice.status}")
