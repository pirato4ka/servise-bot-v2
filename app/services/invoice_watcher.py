"""
Фоновая проверка неоплаченных счетов.

Без неё оплата засчитывалась только в момент, когда кто-то нажал кнопку
«Проверить оплату». Теперь бот сам опрашивает CryptoBot и фиксирует оплату.
"""
import asyncio
import logging

from aiogram import Bot

from app.config import settings
from app.database import crud
from app.handlers.admin.payment_check import apply_invoice_payment


async def invoice_watcher(bot: Bot, interval: int = None):
    interval = interval or settings.INVOICE_POLL_INTERVAL
    if not interval or interval <= 0:
        logging.info("INVOICE_WATCHER: отключён (INVOICE_POLL_INTERVAL=0)")
        return

    logging.info(f"INVOICE_WATCHER: запущен, интервал {interval} сек")
    while True:
        try:
            await asyncio.sleep(interval)
            pending = await crud.get_pending_invoices()
            if not pending:
                continue
            for record in pending:
                try:
                    await apply_invoice_payment(bot, record["crypto_invoice_id"])
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logging.error(f"INVOICE_WATCHER: ошибка по инвойсу {record['crypto_invoice_id']}: {e}")
        except asyncio.CancelledError:
            logging.info("INVOICE_WATCHER: остановлен")
            raise
        except Exception as e:
            logging.error(f"INVOICE_WATCHER: ошибка цикла: {e}")
