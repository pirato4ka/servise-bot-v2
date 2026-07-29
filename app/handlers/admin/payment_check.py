import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.services.cryptopay import get_invoice_status
from app.database import crud
from app.data.texts import t

router = Router()


# Проверка оплаты пользователем
@router.callback_query(F.data.startswith("checkpay:"))
async def user_check_pay(cb: CallbackQuery):
    crypto_id = int(cb.data.split(":")[1])
    invoice = await get_invoice_status(crypto_id)
    
    if not invoice:
        lang = await crud.get_user_lang(cb.from_user.id)
        await cb.answer(t("invoice_not_found", lang), show_alert=True)
        return

    lang = await crud.get_user_lang(cb.from_user.id)

    if invoice.status == "paid":
        await crud.update_invoice_status(crypto_id, "paid")
        await cb.message.answer(t("invoice_paid_user", lang).format(amount=invoice.amount, asset=invoice.asset))
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
        await crud.update_invoice_status(crypto_id, "paid")
        from app.database.db import get_db
        db = await get_db()
        async with db.execute("SELECT * FROM invoices WHERE crypto_invoice_id=?", (crypto_id,)) as cur:
            row = await cur.fetchone()
        await db.close()
        await cb.message.reply(f"✅ <b>Оплачен!</b>\n\nСумма: {invoice.amount} {invoice.asset}\nUser: {row['user_id'] if row else '?'}\nID: {crypto_id}")
        await cb.answer("Оплачен")
    elif invoice.status == "active":
        await cb.answer(f"⏳ Еще не оплачен. Статус: {invoice.status}\nСумма: {invoice.amount} {invoice.asset}")
    else:
        await cb.answer(f"Статус: {invoice.status}")
