"""
Регрессии третьего круга правок.

Все проверки идут через фейковую сессию, которая ведёт себя как настоящий
Telegram: отбраковывает невалидный HTML (parse_mode=HTML включён по умолчанию,
как в app/bot.py) и следит за лимитами длины (4096 в сообщении, 1024 в подписи).
Раньше тесты этого не проверяли, и баги «сообщение молча теряется» доезжали до прода.

Что здесь покрыто:
  • спецсимволы в имени/тексте клиента больше не роняют отправку (заявки не теряются);
  • длинные подписи к медиа и длинные ответы админа доезжают целиком;
  • выключенная услуга не продаётся;
  • оплата проводится ровно один раз (гонка вотчера и кнопки);
  • язык сохраняется, даже если строки пользователя в БД нет;
  • ID услуги с двоеточием не ломает кнопки админ-панели;
  • сообщения без from_user не роняют обработчики админ-чата.
"""
import asyncio
from datetime import datetime

import pytest
from aiogram.types import Chat, Message, PhotoSize, Update

from app.database import crud
from app.handlers.admin import broadcast as broadcast_module
from app.handlers.admin import payment_check
from app.services import cryptopay
from app.utils.callbacks import cb_args
from app.utils.text import (
    CAPTION_LIMIT,
    MESSAGE_LIMIT,
    esc,
    first_emoji,
    fit,
    format_amount,
    strip_tags,
    truncate,
)
from tests.conftest import ADMIN_CHAT_ID, ADMIN_ID, USER_ID, cb_update, message, msg_update, user

RU_USER = 555000222


async def _fill_questionnaire(dp, bot, chat_id=USER_ID, name="Иван", age="25", recipient="Мне"):
    """Полный путь клиента: /start → язык → услуга → анкета. Возвращает заявку."""
    await dp.feed_update(bot, msg_update(message("/start", chat_id=chat_id, from_user=user(chat_id))))
    await dp.feed_update(bot, cb_update("lang:ua", message(chat_id=chat_id), from_user=user(chat_id)))
    await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=chat_id), from_user=user(chat_id)))
    await dp.feed_update(bot, msg_update(message(name, chat_id=chat_id, from_user=user(chat_id))))
    await dp.feed_update(bot, msg_update(message(age, chat_id=chat_id, from_user=user(chat_id))))
    await dp.feed_update(bot, msg_update(message(recipient, chat_id=chat_id, from_user=user(chat_id))))
    return await crud.get_last_ticket_by_user(chat_id)


async def _admin_reply(dp, bot, ticket, text, message_id=5001):
    await dp.feed_update(bot, msg_update(
        message(text, chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                from_user=user(ADMIN_ID), message_id=message_id,
                reply_to_message=message("заявка", chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                         from_user=user(ADMIN_ID),
                                         message_id=ticket["admin_message_id"]))))


def _photo_msg(chat_id, caption=None, from_user=None):
    return message(
        chat_id=chat_id, caption=caption, from_user=from_user,
        photo=[PhotoSize(file_id="photo-file-id", file_unique_id="uniq", width=800, height=600)],
    )


# ─────────────────────────────────────────────────────────────
#  Спецсимволы клиента не должны терять данные
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["Tom & Jerry", "A <b>B</b>", "100% <гарантия>", "Ж&К «<Заря>»"])
async def test_special_chars_in_name_do_not_lose_ticket(dp, bot, service, name):
    """Имя с «&»/«<» роняло отправку заявки: клиенту «принято», админу — ничего."""
    await _fill_questionnaire(dp, bot, name=name)

    ticket = await crud.get_last_ticket_by_user(USER_ID)
    assert ticket is not None, f"заявка не создалась для имени {name!r}"

    admin_texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert any("НОВАЯ ЗАЯВКА" in t for t in admin_texts), admin_texts


async def test_user_message_with_special_chars_reaches_admin(dp, bot, service):
    """Свободное сообщение клиента со спецсимволами доходит в админ-чат."""
    await _fill_questionnaire(dp, bot)
    bot.session.clear()

    await dp.feed_update(bot, msg_update(message("торг < 100 & срочно", chat_id=USER_ID)))

    texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert texts, "сообщение клиента потеряно"
    assert any("торг" in t for t in texts), texts


async def test_admin_reply_with_special_chars_reaches_user(dp, bot, service):
    """Ответ админа со спецсимволами доходит клиенту."""
    ticket = await _fill_questionnaire(dp, bot)
    bot.session.clear()

    await _admin_reply(dp, bot, ticket, "скидка <b>5%</b> & только сегодня")

    texts = bot.session.texts_to(USER_ID)
    assert texts, f"ответ админа потерян: {bot.session.all_texts()}"
    assert any("5%" in t for t in texts), texts


async def test_users_command_survives_html_names(dp, bot, service):
    """/users падал целиком, если в анкете встречались HTML-спецсимволы."""
    await crud.upsert_user(USER_ID, "tester", "Full <Name>")
    await crud.update_user_questionnaire(USER_ID, "A & B", 25, "me", "test_service")
    await crud.add_admin(ADMIN_ID)
    bot.session.clear()

    await dp.feed_update(bot, msg_update(message("/users", chat_id=ADMIN_ID, from_user=user(ADMIN_ID))))

    texts = bot.session.texts_to(ADMIN_ID)
    assert texts, "/users не вернул ничего"
    assert str(USER_ID) in texts[0]


async def test_decline_reason_with_special_chars(dp, bot, service):
    """Причина отклонения со спецсимволами доезжает до клиента."""
    ticket = await _fill_questionnaire(dp, bot)
    await dp.feed_update(bot, cb_update(
        f"ticket:decline:{ticket['admin_message_id']}",
        message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID)),
        from_user=user(ADMIN_ID),
    ))
    bot.session.clear()
    await dp.feed_update(bot, msg_update(
        message("не прошли проверку <18> & лимит", chat_id=ADMIN_CHAT_ID,
                chat_type="supergroup", from_user=user(ADMIN_ID))))

    texts = bot.session.texts_to(USER_ID)
    assert texts, "отклонение не отправлено клиенту"
    assert any("відхилено" in t for t in texts), texts


async def test_deep_link_source_with_garbage(dp, bot, service):
    """Источник из /start попадает в HTML-шаблон — мусор не должен его рвать."""
    await dp.feed_update(bot, msg_update(
        message("/start <script>alert(1)</script> & co", chat_id=USER_ID)))
    await dp.feed_update(bot, cb_update("lang:ua", message(chat_id=USER_ID)))

    assert bot.session.texts_to(USER_ID), "приветствие не отправлено"
    row = await crud.get_user(USER_ID)
    assert "<" not in (row["source"] or ""), row["source"]


# ─────────────────────────────────────────────────────────────
#  Лимиты Telegram
# ─────────────────────────────────────────────────────────────

async def test_photo_with_long_caption_from_user(dp, bot, service):
    """Подпись к фото длиннее 1024 символов: медиа и текст доходят в админ-чат."""
    await _fill_questionnaire(dp, bot)
    bot.session.clear()

    long_caption = "детали сделки " * 120  # ~1800 символов
    await dp.feed_update(bot, msg_update(_photo_msg(USER_ID, caption=long_caption)))

    photos = [c for c in bot.session.calls if type(c).__name__ == "SendPhoto"]
    assert photos, "фото не дошло до админ-чата"
    assert len(photos[0].caption) <= CAPTION_LIMIT

    # сам текст клиента при этом не потерялся — уехал отдельным сообщением
    admin_texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert any("детали сделки" in t for t in admin_texts), admin_texts


async def test_long_admin_reply_is_delivered(dp, bot, service):
    """Ответ админа на 4000+ символов не теряется из-за лимита сообщения."""
    ticket = await _fill_questionnaire(dp, bot)
    bot.session.clear()

    await _admin_reply(dp, bot, ticket, "а" * 4090)

    texts = bot.session.texts_to(USER_ID)
    assert texts, "длинный ответ админа потерян"
    assert all(len(t) <= MESSAGE_LIMIT for t in texts)
    assert any("а" * 100 in t for t in texts), "текст ответа обрезан до неузнаваемости"


async def test_admin_photo_with_long_caption(dp, bot, service):
    """Фото от админа с длинной подписью: клиент получает и медиа, и текст."""
    ticket = await _fill_questionnaire(dp, bot)
    bot.session.clear()

    await dp.feed_update(bot, msg_update(message(
        chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID), message_id=5002,
        caption="инструкция " * 150,
        photo=[PhotoSize(file_id="admin-photo", file_unique_id="uniq2", width=100, height=100)],
        reply_to_message=message("заявка", chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                 from_user=user(ADMIN_ID), message_id=ticket["admin_message_id"]),
    )))

    photos = [c for c in bot.session.calls if type(c).__name__ == "SendPhoto"]
    assert photos, "фото не дошло клиенту"
    assert len(photos[0].caption) <= CAPTION_LIMIT
    assert any("инструкция" in t for t in bot.session.texts_to(USER_ID))


async def test_long_service_button_label_rejected(dp, bot, service):
    """Кнопка длиннее 64 символов не пускается в базу — иначе клавиатура падает целиком."""
    await dp.feed_update(bot, cb_update(
        "svc:add", message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID)),
        from_user=user(ADMIN_ID)))
    long_label = "🔘 " + "очень длинное название кнопки " * 5
    for step in ["long_svc", "🔘", "Назва", "Название", "о", "о", "у", "у", long_label]:
        await dp.feed_update(bot, msg_update(
            message(step, chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID))))

    texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert any("64" in t for t in texts), texts[-2:]
    assert await crud.get_service_by_id("long_svc") is None


async def test_keyboard_survives_long_button_label(dp, bot, service):
    """Слишком длинная метка кнопки ужимается, и услуга по-прежнему открывается."""
    from app.keyboards.reply import get_services_keyboard

    await crud.create_service({
        "id": "longone", "emoji": "📏", "title_ua": "Довга", "title_ru": "Длинная",
        # наследие старых баз: метка длиннее лимита Telegram в 64 символа
        "button_label_ua": "📏 Дуже довга назва кнопки",
        "button_label_ru": "📏 " + "д" * 90,
        "short_desc_ua": "s", "short_desc_ru": "s", "terms_ua": "t", "terms_ru": "t",
    })

    kb = await get_services_keyboard("ru")
    labels = [b.text for row in kb.keyboard for b in row]
    assert all(len(label) <= 64 for label in labels), labels

    long_label = next(label for label in labels if label.startswith("📏"))
    assert len(long_label) == 64
    found = await crud.get_service_by_button(long_label)
    assert found is not None and found["id"] == "longone", found


async def test_keyboard_deduplicates_same_label(dp, bot, service):
    """Два одинаковых текста кнопок (UA одной и RU другой услуги) не рвут клавиатуру."""
    from app.keyboards.reply import get_services_keyboard

    await crud.create_service({
        "id": "twin", "emoji": "🔒", "title_ua": "Твін", "title_ru": "Твин",
        # пустая UA-метка -> localize_service откатится на RU, а она равна UA-метке
        # существующей услуги: Telegram такие клавиатуры отбраковывает целиком
        "button_label_ua": "",
        "button_label_ru": service["button_label_ua"],
        "short_desc_ua": "s", "short_desc_ru": "s", "terms_ua": "t", "terms_ru": "t",
    })

    kb = await get_services_keyboard("ua")
    labels = [b.text for row in kb.keyboard for b in row]
    assert labels, "клавиатура осталась пустой"
    assert len(labels) == len(set(labels)), f"дубли кнопок: {labels}"


# ─────────────────────────────────────────────────────────────
#  Статусы услуг
# ─────────────────────────────────────────────────────────────

async def test_disabled_service_cannot_be_ordered(dp, bot, service):
    """«🔴 Выключить» в админке действительно закрывает продажу."""
    await dp.feed_update(bot, msg_update(message("/start", chat_id=USER_ID, from_user=user(USER_ID))))
    await dp.feed_update(bot, cb_update("lang:ua", message(chat_id=USER_ID), from_user=user(USER_ID)))
    await crud.toggle_service("test_service")

    # старая клавиатура у клиента ещё открыта — жмёт выключенную услугу
    await dp.feed_update(bot, msg_update(message("🔒 Тестова послуга", chat_id=USER_ID, from_user=user(USER_ID))))

    texts = bot.session.texts_to(USER_ID)
    assert any("недоступна" in t for t in texts), texts
    assert not any("Погоджуюсь" in str(c) for c in bot.session.calls), "выключенную услугу всё ещё продают"

    # и через колбек согласиться тоже нельзя
    await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=USER_ID), from_user=user(USER_ID)))
    assert await crud.get_last_ticket_by_user(USER_ID) is None


async def test_disabled_service_not_forwarded_as_free_message(dp, bot, service):
    """Нажатие выключенной кнопки не улетает в админ-чат как «свободное сообщение»."""
    await _fill_questionnaire(dp, bot)
    await crud.toggle_service("test_service")
    bot.session.clear()

    await dp.feed_update(bot, msg_update(message("🔒 Тестова послуга", chat_id=USER_ID, from_user=user(USER_ID))))

    assert bot.session.texts_to(ADMIN_CHAT_ID) == [], bot.session.texts_to(ADMIN_CHAT_ID)


# ─────────────────────────────────────────────────────────────
#  Оплата: ровно один раз
# ─────────────────────────────────────────────────────────────

def _paid_invoice(invoice_id=4242, amount="100", asset="USDT"):
    return cryptopay.CryptoInvoice({
        "invoice_id": invoice_id, "status": "paid", "asset": asset, "amount": amount,
        "bot_invoice_url": "https://t.me/CryptoBot?start=x", "mini_app_invoice_url": "https://t.me/x",
    })


@pytest.fixture()
def paid_api(monkeypatch):
    async def _get_invoice_status(invoice_id):
        return _paid_invoice(invoice_id)

    async def _get_invoices_statuses(invoice_ids):
        return {int(i): _paid_invoice(int(i)) for i in invoice_ids}

    monkeypatch.setattr(payment_check, "get_invoice_status", _get_invoice_status)
    monkeypatch.setattr(cryptopay, "get_invoices_statuses", _get_invoices_statuses)


async def test_watcher_requests_statuses_in_batches(bot, monkeypatch):
    """Фоновый вотчер опрашивает счета пачками: 120 счетов — это 3 запроса, а не 120."""
    from app.services.invoice_watcher import invoice_watcher

    batches = []

    async def fake_statuses(invoice_ids):
        batches.append(list(invoice_ids))
        return {}

    monkeypatch.setattr(cryptopay, "get_invoices_statuses", fake_statuses)

    await crud.upsert_user(USER_ID, "t", "T")
    total = 120
    for i in range(total):
        await crud.create_invoice_record(1000 + i, USER_ID, None, "USDT", "10", "u", "m", "p")

    task = asyncio.create_task(invoice_watcher(bot, interval=0.05))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert batches, "вотчер вообще не опросил счета"
    first_cycle = batches[:3]
    assert sum(len(b) for b in first_cycle) == total, first_cycle
    assert all(len(b) <= cryptopay.MAX_IDS_PER_REQUEST for b in batches), [len(b) for b in batches]


async def test_payment_button_does_not_duplicate_notification(dp, bot, service, paid_api):
    """Кнопка «Проверить оплату» больше не шлёт клиенту второе такое же сообщение."""
    ticket = await _fill_questionnaire(dp, bot)
    await crud.create_invoice_record(4242, USER_ID, ticket["id"], "USDT", "100", "u", "m", "p")

    await dp.feed_update(bot, cb_update("checkpay:4242", message(chat_id=USER_ID), from_user=user(USER_ID)))

    texts = bot.session.texts_to(USER_ID)
    assert sum("підтверджено" in t for t in texts) == 1, texts
    assert (await crud.get_ticket_by_id(ticket["id"]))["status"] == "paid"


async def test_mark_invoice_paid_is_atomic(service):
    """Вотчер и кнопка, сработав одновременно, проводят оплату один раз."""
    await crud.upsert_user(USER_ID, "t", "T")
    ticket_id = await crud.create_ticket(USER_ID, 7001, ADMIN_CHAT_ID, "test_service")
    await crud.create_invoice_record(4242, USER_ID, ticket_id, "USDT", "100", "u", "m", "p")

    results = await asyncio.gather(*(crud.mark_invoice_paid(4242) for _ in range(5)))

    assert sum(1 for r in results if r) == 1, results
    assert (await crud.get_ticket_by_id(ticket_id))["status"] == "paid"


async def test_admin_check_requires_admin_rights(dp, bot, service, paid_api):
    """Кнопка админ-проверки счёта не работает у постороннего пользователя."""
    ticket = await _fill_questionnaire(dp, bot)
    await crud.create_invoice_record(4242, USER_ID, ticket["id"], "USDT", "100", "u", "m", "p")
    bot.session.clear()

    await dp.feed_update(bot, cb_update(
        "admin_check:4242", message(chat_id=999), from_user=user(999)))

    assert (await crud.get_ticket_by_id(ticket["id"]))["status"] == "open"
    answers = [c for c in bot.session.calls if type(c).__name__ == "AnswerCallbackQuery"]
    assert answers and answers[-1].text == "Недоступно", answers


async def test_broken_callback_data_does_not_crash(dp, bot, service, paid_api):
    """Битые данные кнопки не роняют обработчик (ValueError на int())."""
    await dp.feed_update(bot, cb_update("checkpay:not-a-number", message(chat_id=USER_ID),
                                        from_user=user(USER_ID)))
    await dp.feed_update(bot, cb_update("admin_check:", message(chat_id=ADMIN_CHAT_ID,
                                                               chat_type="supergroup",
                                                               from_user=user(ADMIN_ID)),
                                        from_user=user(ADMIN_ID)))
    answers = [c for c in bot.session.calls if type(c).__name__ == "AnswerCallbackQuery"]
    assert answers, "на битые кнопки никто не ответил — у пользователя остались «часики»"


# ─────────────────────────────────────────────────────────────
#  Рассылка
# ─────────────────────────────────────────────────────────────

async def test_broadcast_with_broken_html_still_delivered(bot):
    """Один лишний «<» в тексте рассылки больше не хоронит всю рассылку."""
    await crud.upsert_user(101, "u101", "User 101")
    await crud.upsert_user(102, "u102", "User 102")
    bid = await crud.create_broadcast(ADMIN_ID, 24, "Акция < 50% & скидки", None)

    result = await broadcast_module.run_broadcast(bot, bid, "Акция < 50% & скидки", None)

    assert result["sent"] == 2 and result["failed"] == 0, result
    assert bot.session.texts_to(101) == ["Акция < 50% & скидки"]


async def test_broadcast_survives_single_iteration_error(bot, monkeypatch):
    """Ошибка одной итерации не убивает регулярную рассылку навсегда."""
    calls = []

    async def flaky_run(bot_, broadcast_id, text, photo):
        calls.append(broadcast_id)
        if len(calls) == 1:
            raise RuntimeError("telegram лёг")
        return {}

    monkeypatch.setattr(broadcast_module, "run_broadcast", flaky_run)

    bid = await crud.create_broadcast(ADMIN_ID, 1 / 3600, "Текст", None)  # раз в секунду
    task = asyncio.create_task(
        broadcast_module.broadcast_loop(bot, bid, interval_hours=1 / 3600, initial_delay=0)
    )
    await asyncio.sleep(1.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(calls) >= 2, f"цикл рассылки остановился после первой ошибки: {calls}"


async def test_broadcasts_list_survives_html_text(dp, bot, service):
    """/broadcasts не падает, если текст рассылки — HTML (превью режет теги)."""
    await crud.add_admin(ADMIN_ID)
    await crud.create_broadcast(ADMIN_ID, 24, "<b>Скидки</b> до 50% <a href='https://x'>тут</a>", None)

    await dp.feed_update(bot, msg_update(
        message("/broadcasts", chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID))))

    texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert texts, "/broadcasts ничего не вернул"
    assert "Скидки" in texts[0]


# ─────────────────────────────────────────────────────────────
#  Язык и состояние пользователя
# ─────────────────────────────────────────────────────────────

async def test_language_saved_even_without_user_row(dp, bot, service):
    """Нет строки в users — язык всё равно сохраняется (раньше выбор зацикливался)."""
    await dp.feed_update(bot, msg_update(message("/start", chat_id=USER_ID, from_user=user(USER_ID))))

    from app.database.db import get_db
    db = await get_db()
    await db.execute("DELETE FROM users")
    await db.commit()
    await db.close()

    await dp.feed_update(bot, cb_update("lang:ru", message(chat_id=USER_ID), from_user=user(USER_ID)))

    assert await crud.get_user_lang(USER_ID) == "ru"
    assert await crud.get_user(USER_ID) is not None


async def test_cancel_keeps_user_language(dp, bot, service):
    """После отмены анкеты клавиатура услуг — на языке клиента."""
    await dp.feed_update(bot, msg_update(message("/start", chat_id=RU_USER, from_user=user(RU_USER))))
    await dp.feed_update(bot, cb_update("lang:ru", message(chat_id=RU_USER), from_user=user(RU_USER)))
    await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=RU_USER), from_user=user(RU_USER)))
    bot.session.clear()

    await dp.feed_update(bot, msg_update(message("❌ Отменить", chat_id=RU_USER, from_user=user(RU_USER))))

    last = [c for c in bot.session.calls if type(c).__name__ == "SendMessage"][-1]
    assert "Тестовая услуга" in str(last.reply_markup.keyboard), last.reply_markup.keyboard


async def test_service_with_broken_html_terms_still_shown(dp, bot, service):
    """Битый HTML в условиях услуги не оставляет клиента с пустым экраном."""
    await crud.update_service_field("test_service", "terms_ru", "Условия <без тега & косяк")
    await dp.feed_update(bot, msg_update(message("/start", chat_id=RU_USER, from_user=user(RU_USER))))
    await dp.feed_update(bot, cb_update("lang:ru", message(chat_id=RU_USER), from_user=user(RU_USER)))
    bot.session.clear()

    await dp.feed_update(bot, msg_update(message("🔒 Тестовая услуга", chat_id=RU_USER, from_user=user(RU_USER))))

    texts = bot.session.texts_to(RU_USER)
    assert texts, "условия услуги не показали"
    assert any("Условия" in t for t in texts), texts


# ─────────────────────────────────────────────────────────────
#  Админ-панель и служебные апдейты
# ─────────────────────────────────────────────────────────────

async def test_legacy_service_id_with_colon(dp, bot, service):
    """ID услуги с двоеточием (старые данные) не ломает кнопки панели."""
    await crud.create_service({
        "id": "vip:gold", "emoji": "👑", "title_ua": "VIP", "title_ru": "VIP",
        "button_label_ua": "👑 VIP", "button_label_ru": "👑 VIP",
        "short_desc_ua": "s", "short_desc_ru": "s", "terms_ua": "t", "terms_ru": "t",
    })
    bot.session.clear()

    await dp.feed_update(bot, cb_update(
        "svc:view:vip:gold",
        message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID)),
        from_user=user(ADMIN_ID)))

    answers = [c for c in bot.session.calls if type(c).__name__ == "AnswerCallbackQuery"]
    assert not any(c.text == "Не найдено" for c in answers), answers
    edits = [c for c in bot.session.calls if type(c).__name__ == "EditMessageText"]
    assert edits and "vip:gold" in edits[0].text


async def test_wizard_rejects_invalid_service_id(dp, bot, service):
    """Новый ID услуги валидируется: двоеточия и пробелы в кнопки не попадут."""
    await dp.feed_update(bot, cb_update(
        "svc:add", message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID)),
        from_user=user(ADMIN_ID)))
    await dp.feed_update(bot, msg_update(
        message("bad:id", chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID))))

    texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert any("допустимы только латинские" in t for t in texts), texts[-2:]

    # корректный ID после этого принимается
    await dp.feed_update(bot, msg_update(
        message("good_id", chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID))))
    texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert any("эмодзи" in t for t in texts), texts[-2:]


async def test_message_without_from_user_in_admin_chat(dp, bot, service):
    """Пост из привязанного канала (from_user=None) не роняет авто-регистрацию админов."""
    msg = Message(
        message_id=9001, date=datetime.now(), text="пост из канала",
        chat=Chat(id=ADMIN_CHAT_ID, type="supergroup"),
    )
    await dp.feed_update(bot, Update(update_id=9001, message=msg))
    assert await crud.get_admins() == []


async def test_edit_service_after_state_lost(dp, bot, service):
    """Правка поля после потери состояния отвечает внятно, а не падает."""
    from aiogram.fsm.storage.memory import StorageKey

    await dp.feed_update(bot, cb_update(
        "svc:editfield:test_service:ru:title",
        message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID)),
        from_user=user(ADMIN_ID)))
    # имитируем потерю данных состояния (рестарт бота между шагами):
    # состояние осталось, а edit_sid/edit_field пропали
    key = StorageKey(bot_id=bot.id, chat_id=ADMIN_CHAT_ID, user_id=ADMIN_ID)
    await dp.storage.set_data(key=key, data={})

    bot.session.clear()
    await dp.feed_update(bot, msg_update(
        message("Новое название", chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID))))

    texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert any("потеряны" in t for t in texts), texts
    svc = await crud.get_service_by_id("test_service")
    assert svc["title_ru"] == "Тестовая услуга", "поле изменилось без данных состояния"


# ─────────────────────────────────────────────────────────────
#  Юнит-проверки утилит
# ─────────────────────────────────────────────────────────────

def test_esc_and_strip_tags():
    assert esc("Tom & <Jerry>") == "Tom &amp; &lt;Jerry&gt;"
    assert esc(None) == ""
    assert strip_tags("<b>Скидки</b> до 50%") == "Скидки до 50%"


def test_truncate_and_fit():
    assert truncate("abcdef", 6) == "abcdef"
    assert truncate("abcdefg", 4) == "abc…"
    template = "Заголовок: {body}"
    assert len(fit(template, 20, body="ы" * 500)) == 20
    # fit не трогает текст, если подставлять нечего (фигурные скобки клиента)
    assert fit("текст с {0} скобками", 100) == "текст с {0} скобками"


def test_format_amount():
    assert format_amount(100.0) == "100"
    assert format_amount("0.05000000") == "0.05"
    assert format_amount(1234.5678) == "1234.5678"
    assert format_amount("USDT") == "USDT"


def test_first_emoji_keeps_composite_glyphs():
    assert first_emoji("🛡️ Безпечна угода") == "🛡️"
    assert first_emoji("👨‍👩‍👦 Родному") == "👨‍👩‍👦"
    assert first_emoji("🇺🇦 Україна") == "🇺🇦"
    assert first_emoji("🔥💎 два") == "🔥💎"
    assert first_emoji("") == ""


def test_cb_args_tolerates_colons_in_service_id():
    assert cb_args("svc:view:vip:gold", "svc:view:") == ("vip:gold",)
    assert cb_args("svc:editlang:vip:gold:ru", "svc:editlang:", tail=1) == ("vip:gold", "ru")
    assert cb_args("svc:editfield:vip:gold:ua:title", "svc:editfield:", tail=2) == (
        "vip:gold", "ua", "title",
    )
    assert cb_args("svc:editlang:broken", "svc:editlang:", tail=1) == ("", "")


def test_parse_price():
    from app.handlers.admin.confirm_payment import parse_price

    assert parse_price("100 USDT") == (100.0, "USDT")
    assert parse_price("0,05 btc") == (0.05, "BTC")
    assert parse_price("0 USDT") is None
    assert parse_price("100") is None
    assert parse_price("abc USDT") is None
    assert parse_price("") is None
