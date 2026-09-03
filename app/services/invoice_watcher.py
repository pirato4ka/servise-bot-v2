"""
Фоновая проверка неоплаченных счетов.

Без неё оплата засчитывалась только в момент, когда кто-то нажал кнопку
«Проверить оплату». Теперь бот сам опрашивает CryptoBot и фиксирует оплату.

Статусы запрашиваются пачками (см. cryptopay.get_invoices_statuses): поштучный
опрос давал по запросу на каждый счёт каждую минуту и упирался в лимит выборки,
из-за чего старые неоплаченные счета переставали проверяться вовсе.
"""
import asyncio
import logging

from aiogram import Bot

from app.config import settings
from app.database import crud
from app.handlers.admin.payment_check import apply_invoice_payment
from app.services import cryptopay

# Сколько неоплаченных счетов держать в поле зрения за один проход
PENDING_LIMIT = 500
BATCH_SIZE = cryptopay.MAX_IDS_PER_REQUEST


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


async def invoice_watcher(bot: Bot, interval: int = None):
    interval = interval or settings.INVOICE_POLL_INTERVAL
    if not interval or interval <= 0:
        logging.info("INVOICE_WATCHER: отключён (INVOICE_POLL_INTERVAL=0)")
        return

    logging.info(f"INVOICE_WATCHER: запущен, интервал {interval} сек")
    while True:
        try:
            await asyncio.sleep(interval)
            pending = await crud.get_pending_invoices(limit=PENDING_LIMIT)
            if not pending:
                continue
            if len(pending) >= PENDING_LIMIT:
                logging.warning(
                    f"INVOICE_WATCHER: неоплаченных счетов больше {PENDING_LIMIT} — "
                    "часть старых не проверяется фоном (кнопка «Проверить оплату» работает всегда)"
                )

            for batch in _chunks(pending, BATCH_SIZE):
                ids = [record["crypto_invoice_id"] for record in batch if record["crypto_invoice_id"]]
                if not ids:
                    continue
                try:
                    statuses = await cryptopay.get_invoices_statuses(ids)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logging.error(f"INVOICE_WATCHER: не удалось получить статусы пачки: {e}")
                    continue

                for record in batch:
                    invoice = statuses.get(record["crypto_invoice_id"])
                    if not invoice or invoice.status != "paid":
                        continue
                    try:
                        await apply_invoice_payment(
                            bot, record["crypto_invoice_id"], invoice=invoice
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logging.error(f"INVOICE_WATCHER: ошибка по инвойсу {record['crypto_invoice_id']}: {e}")
        except asyncio.CancelledError:
            logging.info("INVOICE_WATCHER: остановлен")
            raise
        except Exception as e:
            logging.error(f"INVOICE_WATCHER: ошибка цикла: {e}")
