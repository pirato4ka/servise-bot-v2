"""
Проверки исправленных багов:
 — закрепление сообщения больше не вызывает «Не удалось определить тикет»;
 — админы сохраняются после перезапуска и синхронизируются с составом группы;
 — рассылки восстанавливаются после перезапуска;
 — reply на reply любой вложенности находит заявку;
 — оплата фиксируется один раз и без нажатия кнопки.
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from app.handlers.admin import broadcast as broadcast_module
from app.config import settings
from app.database import crud
from app.handlers.admin import membership, payment_check
from app.handlers.admin.payment_check import apply_invoice_payment
from app.services import cryptopay
from app.services.invoice_watcher import invoice_watcher
from tests.conftest import (
    ADMIN_CHAT_ID, ADMIN_ID, USER_ID, admin_member, cb_update, message, msg_update, user,
)

WARNING = "Не удалось определить тикет"


async def _create_ticket(dp, bot):
    """Прогоняет анкету и возвращает (ticket, admin_message_id)."""
    await dp.feed_update(bot, msg_update(message("/start", chat_id=USER_ID)))
    await dp.feed_update(bot, cb_update("lang:ua", message(chat_id=USER_ID)))
    await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("Иван", chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("25", chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("Мне", chat_id=USER_ID)))
    ticket = await crud.get_last_ticket_by_user(USER_ID)
    return ticket, ticket["admin_message_id"]


def _pinned_update(pinned_message_id: int, reply_to_id: int = None, chat_id: int = ADMIN_CHAT_ID):
    """Служебное сообщение о закреплении (Telegram присылает его как reply)."""
    pinned = message("закреплённый текст", chat_id=chat_id, chat_type="supergroup",
                     from_user=user(ADMIN_ID), message_id=pinned_message_id)
    return msg_update(
        message(
            chat_id=chat_id,
            chat_type="supergroup",
            from_user=user(ADMIN_ID),
            pinned_message=pinned,
            reply_to_message=pinned if reply_to_id is None else message(
                "другое сообщение", chat_id=chat_id, chat_type="supergroup",
                from_user=user(ADMIN_ID), message_id=reply_to_id,
            ),
        )
    )


# ─────────────────────────────────────────────────────────────
#  БАГ: закрепление сообщения
# ─────────────────────────────────────────────────────────────

async def test_pin_of_random_message_no_warning(dp, bot, service):
    """Пин случайного сообщения: раньше бот отвечал «Не удалось определить тикет»."""
    await _create_ticket(dp, bot)
    bot.session.clear()

    await dp.feed_update(bot, _pinned_update(pinned_message_id=9001, reply_to_id=4242))

    admin_texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert not any(WARNING in t for t in admin_texts), admin_texts
    assert not any("Отправь текст" in t for t in admin_texts), admin_texts


async def test_pin_of_ticket_message_silent(dp, bot, service):
    """Пин самой заявки: ни предупреждения, ни пустого сообщения пользователю."""
    ticket, admin_msg_id = await _create_ticket(dp, bot)
    bot.session.clear()

    await dp.feed_update(bot, _pinned_update(pinned_message_id=admin_msg_id))

    assert not any(WARNING in t for t in bot.session.texts_to(ADMIN_CHAT_ID))
    assert bot.session.texts_to(USER_ID) == [], bot.session.texts_to(USER_ID)


async def test_service_events_ignored(dp, bot, service):
    """Вход/выход участника и смена названия чата — не ответ по заявке."""
    await _create_ticket(dp, bot)
    bot.session.clear()

    update = msg_update(
        message(
            chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID),
            new_chat_title="Новое название",
            reply_to_message=message("x", chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                     from_user=user(ADMIN_ID), message_id=4243),
        )
    )
    await dp.feed_update(bot, update)
    assert not any(WARNING in t for t in bot.session.texts_to(ADMIN_CHAT_ID))


# ─────────────────────────────────────────────────────────────
#  БАГ: админы после перезапуска
# ─────────────────────────────────────────────────────────────

async def test_admins_survive_restart(bot):
    """Кто уже в группе — остаётся админом; новые добавляются, ушедшие убираются."""
    await crud.add_admin(111)          # был админом до рестарта
    await crud.add_admin(222)          # вышел из группы, пока бот лежал

    bot.session.chat_admins = [admin_member(111), admin_member(333)]  # 333 добавили в группу
    bot.session.chat_member_status = {111: "member", 222: "left"}

    added, removed = await membership.sync_chat_admins(bot)

    assert await crud.is_admin(111), "старый админ потерялся после перезапуска"
    assert await crud.is_admin(333), "новый админ из группы не добавлен"
    assert not await crud.is_admin(222), "ушедший из группы остался админом"
    assert added == 1 and removed == 1


async def test_admins_keep_working_after_restart_with_empty_db(bot):
    """Если база новая (например, контейнер без volume) — админы подтягиваются из группы."""
    bot.session.chat_admins = [admin_member(111), admin_member(222)]
    await membership.sync_chat_admins(bot)

    admins = await crud.get_admins()
    assert {a["user_id"] for a in admins} == {111, 222}


async def test_admins_not_lost_if_chat_unavailable(bot):
    """Нет доступа к чату — ничего не удаляем, чтобы не остаться без админов."""
    await crud.add_admin(111)

    async def boom(*args, **kwargs):
        raise RuntimeError("bot is not a member")

    bot.get_chat_administrators = boom

    added, removed = await membership.sync_chat_admins(bot)
    assert (added, removed) == (0, 0)
    assert await crud.is_admin(111)


# ─────────────────────────────────────────────────────────────
#  БАГ: рассылки после перезапуска
# ─────────────────────────────────────────────────────────────

async def test_broadcast_restored_after_restart(bot, monkeypatch):
    """load_active_broadcasts поднимает задачу из БД (раньше она не вызывалась)."""
    sent = []

    async def fake_run(bot_, broadcast_id, text, photo):
        sent.append((broadcast_id, text))

    monkeypatch.setattr(broadcast_module, "run_broadcast", fake_run)

    bid = await crud.create_broadcast(ADMIN_ID, 24, "Текст рассылки", None)
    # последняя отправка была 25 часов назад — интервал истёк, слать сразу
    from app.database.db import get_db
    db = await get_db()
    await db.execute("UPDATE broadcasts SET last_sent_at=? WHERE id=?",
                     ((datetime.now() - timedelta(hours=25)).isoformat(), bid))
    await db.commit()
    await db.close()

    restored = await broadcast_module.load_active_broadcasts(bot)
    assert restored == 1

    await asyncio.sleep(0.1)
    assert sent == [(bid, "Текст рассылки")], sent

    await broadcast_module.stop_all_broadcasts()


async def test_broadcast_skips_admins_and_banned(bot):
    """Рассылка не должна долбить админов и забаненных."""
    await crud.upsert_user(101, "u101", "User 101")
    await crud.upsert_user(102, "u102", "User 102")
    await crud.upsert_user(103, "u103", "User 103")
    await crud.add_admin(102)
    await crud.ban_user(103)

    bid = await crud.create_broadcast(ADMIN_ID, 24, "Привет всем", None)
    await broadcast_module.run_broadcast(bot, bid, "Привет всем", None)

    assert bot.session.texts_to(101) == ["Привет всем"]
    assert bot.session.texts_to(102) == []
    assert bot.session.texts_to(103) == []


async def test_broadcast_loop_sends_immediately_on_start(bot, monkeypatch):
    """Первая отправка при initial_delay=0 не ждёт интервал."""
    sent = []

    async def fake_run(bot_, broadcast_id, text, photo):
        sent.append(broadcast_id)
        return {}

    monkeypatch.setattr(broadcast_module, "run_broadcast", fake_run)

    bid = await crud.create_broadcast(ADMIN_ID, 24, "Сразу", None)
    task = asyncio.create_task(
        broadcast_module.broadcast_loop(bot, bid, interval_hours=24, initial_delay=0)
    )
    await asyncio.sleep(0.05)
    assert sent == [bid]
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# ─────────────────────────────────────────────────────────────
#  Reply-мост: вложенные ответы
# ─────────────────────────────────────────────────────────────

async def test_reply_chain_any_depth(dp, bot, service):
    """Ответ на ответ на ответ всё равно находит заявку."""
    ticket, admin_msg_id = await _create_ticket(dp, bot)

    # пользователь пишет continuation → в админ-чат уходит новое сообщение
    await dp.feed_update(bot, msg_update(message("А есть ли гарантия?", chat_id=USER_ID)))
    continuation_id = bot.session.message_id

    # админ отвечает на continuation
    await dp.feed_update(bot, msg_update(
        message("Да, гарантия есть", chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                from_user=user(ADMIN_ID), message_id=5001,
                reply_to_message=message("cont", chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                        from_user=user(ADMIN_ID), message_id=continuation_id))
    ))
    assert any("Відповідь від адміністрації" in t for t in bot.session.texts_to(USER_ID))

    # админ отвечает на свой же ответ (второй уровень вложенности)
    await dp.feed_update(bot, msg_update(
        message("И ещё скидка 10%", chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                from_user=user(ADMIN_ID), message_id=5002,
                reply_to_message=message("reply", chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                        from_user=user(ADMIN_ID), message_id=5001))
    ))

    user_texts = bot.session.texts_to(USER_ID)
    assert sum("И ещё скидка 10%" in t for t in user_texts) == 1, user_texts
    assert not any(WARNING in t for t in bot.session.texts_to(ADMIN_CHAT_ID))


# ─────────────────────────────────────────────────────────────
#  Оплата
# ─────────────────────────────────────────────────────────────

def _paid_invoice(amount="100", asset="USDT"):
    return cryptopay.CryptoInvoice({
        "invoice_id": 4242, "status": "paid", "asset": asset, "amount": amount,
        "bot_invoice_url": "https://t.me/CryptoBot?start=x", "mini_app_invoice_url": "https://t.me/x",
    })


@pytest.fixture()
def paid_api(monkeypatch):
    async def _get_invoice_status(invoice_id):
        return _paid_invoice()

    async def _get_invoices_statuses(invoice_ids):
        return {int(i): _paid_invoice() for i in invoice_ids}

    monkeypatch.setattr(payment_check, "get_invoice_status", _get_invoice_status)
    monkeypatch.setattr(cryptopay, "get_invoices_statuses", _get_invoices_statuses)


async def test_invoice_applied_once(dp, bot, service, paid_api):
    """Оплата фиксируется один раз: пользователь и админ получают по одному уведомлению."""
    ticket, admin_msg_id = await _create_ticket(dp, bot)
    await crud.create_invoice_record(4242, USER_ID, ticket["id"], "USDT", "100", "u", "m", "p")

    first = await apply_invoice_payment(bot, 4242)
    assert first is not None
    assert (await crud.get_ticket_by_id(ticket["id"]))["status"] == "paid"

    user_texts = bot.session.texts_to(USER_ID)
    assert sum("Оплату підтверджено" in t for t in user_texts) == 1, user_texts

    second = await apply_invoice_payment(bot, 4242)  # повторно — не должно дублировать
    assert second is None
    assert sum("Оплату підтверджено" in t for t in bot.session.texts_to(USER_ID)) == 1


async def test_invoice_watcher_finds_payment_without_button(dp, bot, service, paid_api):
    """Фоновый вотчер фиксирует оплату, даже если никто не нажал «Проверить оплату»."""
    ticket, _ = await _create_ticket(dp, bot)
    await crud.create_invoice_record(4242, USER_ID, ticket["id"], "USDT", "100", "u", "m", "p")

    task = asyncio.create_task(invoice_watcher(bot, interval=0.05))
    await asyncio.sleep(0.25)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert (await crud.get_ticket_by_id(ticket["id"]))["status"] == "paid"
    assert any("Оплату підтверджено" in t for t in bot.session.texts_to(USER_ID))


async def test_foreign_invoice_not_confirmed(dp, bot, service, paid_api):
    """Чужой счёт нельзя подтвердить со своей кнопки."""
    await crud.upsert_user(999, "other", "Other User")
    ticket = await crud.get_last_ticket_by_user(999)
    assert ticket is None

    await crud.upsert_user(USER_ID, "tester", "Tester")
    ticket_id = await crud.create_ticket(USER_ID, 7001, settings.ADMIN_CHAT_ID, "test_service")
    await crud.create_invoice_record(4242, USER_ID, ticket_id, "USDT", "100", "u", "m", "p")

    # другой пользователь жмёт «проверить оплату» по чужому инвойсу
    await dp.feed_update(bot, cb_update(
        "checkpay:4242",
        message(chat_id=999),
        from_user=user(999),
    ))

    assert (await crud.get_ticket_by_id(ticket_id))["status"] == "open"
    answers = [c for c in bot.session.calls if type(c).__name__ == "AnswerCallbackQuery"]
    assert answers and "не знайдено" in answers[-1].text
