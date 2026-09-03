"""
Двуязычные услуги:
 — админ добавляет услугу сразу на UA и RU (в т.ч. копированием «=»);
 — пользователь видит кнопки, описание и условия на своём языке;
 — смена языка (/lang) перерисовывает интерфейс;
 — старые одноязычные базы автоматически мигрируются.
"""
import sqlite3

from app.database import crud
from tests.conftest import ADMIN_CHAT_ID, ADMIN_ID, cb_update, message, msg_update, user

UA_USER = 555000111
RU_USER = 555000222


async def _press_service(dp, bot, chat_id, label):
    await dp.feed_update(bot, msg_update(message(label, chat_id=chat_id, from_user=user(chat_id))))


async def _set_lang(dp, bot, chat_id, lang):
    await dp.feed_update(bot, msg_update(message("/start", chat_id=chat_id, from_user=user(chat_id))))
    await dp.feed_update(bot, cb_update(f"lang:{lang}", message(chat_id=chat_id), from_user=user(chat_id)))


# ─────────────────────────────────────────────────────────────
#  Мастер добавления услуги админом
# ─────────────────────────────────────────────────────────────

async def test_admin_adds_bilingual_service(dp, bot, service):
    """10 шагов мастера: UA и RU заполняются отдельно."""
    await dp.feed_update(bot, cb_update("svc:add", message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                                           from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))
    steps = [
        "safe_deal", "🛡",
        "Безпечна угода", "Безопасная сделка",
        "Гарантія угоди", "Гарантия сделки",
        "Умови UA", "Условия RU",
        "🛡 Безпечна угода", "🛡 Безопасная сделка",
    ]
    for step in steps:
        await dp.feed_update(bot, msg_update(message(
            step, chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID))))

    svc = await crud.get_service_by_id("safe_deal")
    assert svc is not None, "услуга не создана"
    assert svc["title_ua"] == "Безпечна угода" and svc["title_ru"] == "Безопасная сделка"
    assert svc["terms_ua"] == "Умови UA" and svc["terms_ru"] == "Условия RU"
    assert svc["button_label_ua"] == "🛡 Безпечна угода"
    assert svc["button_label_ru"] == "🛡 Безопасная сделка"

    admin_texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert any("создана на двух языках" in t for t in admin_texts), admin_texts[-3:]


async def test_admin_can_copy_ua_to_ru_with_equals(dp, bot, service):
    """Символ «=» на русском шаге копирует украинский вариант."""
    await dp.feed_update(bot, cb_update("svc:add", message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                                           from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))
    for step in ["fast_doc", "⚡", "Швидкі документи", "=", "Опис UA", "=", "Умови UA", "=",
                 "⚡ Швидкі документи", "="]:
        await dp.feed_update(bot, msg_update(message(
            step, chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID))))

    svc = await crud.get_service_by_id("fast_doc")
    assert svc["title_ru"] == "Швидкі документи"      # скопировано из UA
    assert svc["terms_ru"] == "Умови UA"
    assert svc["button_label_ru"] == "⚡ Швидкі документи"


async def test_duplicate_button_label_rejected(dp, bot, service):
    """Две услуги не могут иметь одинаковую кнопку ни на одном языке."""
    await dp.feed_update(bot, cb_update("svc:add", message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                                           from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))
    for step in ["dupe", "🔁", "Дубль", "Дубль RU", "о", "о", "у", "у",
                 "🔒 Тестова послуга", "🔁 Дубль RU"]:
        await dp.feed_update(bot, msg_update(message(
            step, chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID))))

    texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert any("уже используется" in t for t in texts), texts[-3:]
    assert await crud.get_service_by_id("dupe") is None


async def test_admin_edits_single_field(dp, bot, service):
    """Точечная правка: язык -> поле -> новое значение."""
    await dp.feed_update(bot, cb_update("svc:edit:test_service",
                                        message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                                from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))
    await dp.feed_update(bot, cb_update("svc:editlang:test_service:ru",
                                        message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                                from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))
    await dp.feed_update(bot, cb_update("svc:editfield:test_service:ru:title",
                                        message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                                from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))
    await dp.feed_update(bot, msg_update(message("Новое название", chat_id=ADMIN_CHAT_ID,
                                                 chat_type="supergroup", from_user=user(ADMIN_ID))))

    svc = await crud.get_service_by_id("test_service")
    assert svc["title_ru"] == "Новое название"
    assert svc["title_ua"] == "Тестова послуга", "украинский вариант не должен меняться"


async def test_admin_copies_translation(dp, bot, service):
    """Кнопка «UA → RU» копирует все тексты разом."""
    await dp.feed_update(bot, cb_update("svc:copyua:test_service",
                                        message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                                from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))
    svc = await crud.get_service_by_id("test_service")
    assert svc["title_ru"] == "Тестова послуга"
    assert svc["terms_ru"] == "Умови тестової послуги"


# ─────────────────────────────────────────────────────────────
#  Интерфейс пользователя на его языке
# ─────────────────────────────────────────────────────────────

async def test_user_sees_service_in_his_language(dp, bot, service):
    """UA-пользователь получает украинские название, описание и условия."""
    await _set_lang(dp, bot, UA_USER, "ua")
    await _press_service(dp, bot, UA_USER, "🔒 Тестова послуга")

    texts = bot.session.texts_to(UA_USER)
    joined = "\n".join(texts)
    assert "Тестова послуга" in joined
    assert "Умови тестової послуги" in joined
    assert "Погоджуюсь" in joined


async def test_russian_user_sees_russian_texts(dp, bot, service):
    """RU-пользователь получает русские название, описание и условия."""
    await _set_lang(dp, bot, RU_USER, "ru")
    await _press_service(dp, bot, RU_USER, "🔒 Тестовая услуга")

    joined = "\n".join(bot.session.texts_to(RU_USER))
    assert "Тестовая услуга" in joined
    assert "Условия тестовой услуги" in joined
    assert "Согласен" in joined


async def test_language_switch_rerenders_buttons(dp, bot, service):
    """После /lang клавиатура услуг приходит на новом языке."""
    await _set_lang(dp, bot, UA_USER, "ua")
    kb_before = [c for c in bot.session.calls if type(c).__name__ == "SendMessage"][-1]
    assert "Тестова послуга" in str(kb_before.reply_markup.keyboard)

    await dp.feed_update(bot, msg_update(message("/lang", chat_id=UA_USER, from_user=user(UA_USER))))
    await dp.feed_update(bot, cb_update("lang:ru", message(chat_id=UA_USER), from_user=user(UA_USER)))

    kb_after = [c for c in bot.session.calls if type(c).__name__ == "SendMessage"][-1]
    markup = str(kb_after.reply_markup.keyboard)
    assert "Тестовая услуга" in markup, markup
    assert "Тестова послуга" not in markup, markup


async def test_both_button_labels_open_same_service(dp, bot, service):
    """Нажатие кнопки на любом языке открывает одну и ту же услугу."""
    await _set_lang(dp, bot, UA_USER, "ua")
    await _press_service(dp, bot, UA_USER, "🔒 Тестова послуга")
    ua_texts = "\n".join(bot.session.texts_to(UA_USER))

    await _set_lang(dp, bot, RU_USER, "ru")
    await _press_service(dp, bot, RU_USER, "🔒 Тестовая услуга")
    ru_texts = "\n".join(bot.session.texts_to(RU_USER))

    assert "Умови тестової послуги" in ua_texts
    assert "Условия тестовой услуги" in ru_texts

    # «чужой» вариант кнопки тоже открывает услугу (тексты — по языку пользователя)
    await _press_service(dp, bot, RU_USER, "🔒 Тестова послуга")
    ru_all = "\n".join(bot.session.texts_to(RU_USER))
    assert ru_all.count("Условия тестовой услуги") == 2, "кнопка с UA-текстом не открыла услугу"


async def test_invoice_buttons_localized(dp, bot, service, monkeypatch):
    """Кнопки оплаты приходят на языке пользователя."""
    from app.services import cryptopay

    async def fake_create(asset, amount, description, payload=None, allow_anonymous=True):
        return cryptopay.CryptoInvoice({
            "invoice_id": 777, "status": "active", "asset": asset, "amount": str(amount),
            "bot_invoice_url": "https://t.me/CryptoBot?start=777", "mini_app_invoice_url": "https://t.me/x",
        })

    monkeypatch.setattr("app.handlers.admin.confirm_payment.create_infinite_invoice", fake_create)

    await _set_lang(dp, bot, UA_USER, "ua")
    await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=UA_USER), from_user=user(UA_USER)))
    await dp.feed_update(bot, msg_update(message("Олена", chat_id=UA_USER, from_user=user(UA_USER))))
    await dp.feed_update(bot, msg_update(message("30", chat_id=UA_USER, from_user=user(UA_USER))))
    await dp.feed_update(bot, msg_update(message("Мені", chat_id=UA_USER, from_user=user(UA_USER))))

    # админ подтверждает заявку и выставляет цену
    ticket = await crud.get_last_ticket_by_user(UA_USER)
    await dp.feed_update(bot, cb_update(f"ticket:confirm:{ticket['admin_message_id']}",
                                        message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                                from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))
    await dp.feed_update(bot, msg_update(message("100 USDT", chat_id=ADMIN_CHAT_ID, chat_type="supergroup",
                                                 from_user=user(ADMIN_ID))))

    invoice_msg = [c for c in bot.session.calls
                   if type(c).__name__ == "SendMessage" and getattr(c, "chat_id", None) == UA_USER][-1]
    buttons = [b.text for row in invoice_msg.reply_markup.inline_keyboard for b in row]
    assert "💳 Оплатити через CryptoBot" in buttons, buttons
    assert "🔄 Перевірити оплату" in buttons, buttons


# ─────────────────────────────────────────────────────────────
#  Миграция старой одноязычной базы
# ─────────────────────────────────────────────────────────────

def test_migration_from_single_language_schema(tmp_path):
    """Старая услуга (title/button_label/terms) переносится в оба языка."""
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE services (
            id TEXT PRIMARY KEY, emoji TEXT, title TEXT NOT NULL,
            button_label TEXT NOT NULL UNIQUE, short_desc TEXT, terms TEXT NOT NULL,
            is_active INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO services (id, emoji, title, button_label, short_desc, terms)
        VALUES ('old_one', '🔧', 'Старая услуга', '🔧 Старая услуга', 'описание', 'условия');
    """)
    conn.commit()
    conn.close()

    from app.config import settings
    import app.database.db as db_module

    old_path, settings.DB_PATH = settings.DB_PATH, path
    try:
        import asyncio
        asyncio.run(db_module.init_db())

        conn = sqlite3.connect(path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(services)")]
        row = conn.execute(
            "SELECT title_ua, title_ru, button_label_ua, button_label_ru, terms_ua, terms_ru FROM services"
        ).fetchone()
        conn.close()

        assert "title_ua" in cols and "title_ru" in cols
        assert row == ("Старая услуга", "Старая услуга", "🔧 Старая услуга", "🔧 Старая услуга",
                       "условия", "условия")
    finally:
        settings.DB_PATH = old_path
