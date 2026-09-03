"""
Сквозные проверки основного сценария бота.

Запуск:  .venv311/bin/python -m pytest tests -q
"""


from app.database import crud

from tests.conftest import (
    ADMIN_CHAT_ID, USER_ID, cb_update, message, msg_update, user,
)


async def _start_and_choose_lang(dp, bot, lang="ua"):
    await dp.feed_update(bot, msg_update(message("/start", chat_id=USER_ID, from_user=user())))
    await dp.feed_update(bot, cb_update(f"lang:{lang}", message(chat_id=USER_ID)))


async def _fill_questionnaire(dp, bot, name="Иван", age="25", recipient="Мне"):
    await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message(name, chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message(age, chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message(recipient, chat_id=USER_ID)))


async def test_full_flow_creates_ticket(dp, bot, service):
    """Анкета из 3 шагов → заявка в админ-чате с правильным полем «Кому требуется»."""
    await _start_and_choose_lang(dp, bot, "ua")
    await _fill_questionnaire(dp, bot)

    admin_texts = bot.session.texts_to(ADMIN_CHAT_ID)
    assert any("НОВАЯ ЗАЯВКА" in t for t in admin_texts), admin_texts
    ticket_text = next(t for t in admin_texts if "НОВАЯ ЗАЯВКА" in t)
    assert "Кому требуется:</b> Мне" in ticket_text
    assert "Тестовая услуга" in ticket_text
    assert "Шаг 3/3" not in ticket_text

    ticket = await crud.get_last_ticket_by_user(USER_ID)
    assert ticket is not None
    assert ticket["service_id"] == "test_service"

    db_user = await crud.get_user(USER_ID)
    assert db_user["custom_name"] == "Иван"
    assert db_user["age"] == 25
    assert db_user["recipient"] == "me"

    # Сообщение заявки попало в карту сообщений — reply должен его находить
    linked = await crud.get_admin_message(ticket["admin_message_id"])
    assert linked is not None and linked["ticket_id"] == ticket["id"]


async def test_third_step_accepts_all_recipient_variants(dp, bot, service):
    """Шаг 3/3: Мне / Родному / Другу в любом регистре и с эмодзи."""
    for raw, expected in [
        ("Мне", "me"),
        ("мне", "me"),
        ("👤 Мне", "me"),
        ("Родному", "relative"),
        ("рідному", "relative"),
        ("Другу", "friend"),
        ("друг", "friend"),
    ]:
        await dp.feed_update(bot, msg_update(message("/cancel", chat_id=USER_ID)))
        await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=USER_ID)))
        await dp.feed_update(bot, msg_update(message("Иван", chat_id=USER_ID)))
        await dp.feed_update(bot, msg_update(message("30", chat_id=USER_ID)))
        await dp.feed_update(bot, msg_update(message(raw, chat_id=USER_ID)))

        db_user = await crud.get_user(USER_ID)
        assert db_user["recipient"] == expected, f"'{raw}' -> {db_user['recipient']} != {expected}"


async def test_third_step_rejects_garbage(dp, bot, service):
    """На шаге 3/3 бессмысленный текст не пропускается."""
    await _start_and_choose_lang(dp, bot, "ru")
    await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("Иван", chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("30", chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("когда-нибудь в мае", chat_id=USER_ID)))

    db_user = await crud.get_user(USER_ID)
    assert db_user["recipient"] is None
    assert any("Шаг 3/3" in t for t in bot.session.all_texts()), bot.session.all_texts()

    # правильный ответ всё ещё принимается
    await dp.feed_update(bot, msg_update(message("Другу", chat_id=USER_ID)))
    db_user = await crud.get_user(USER_ID)
    assert db_user["recipient"] == "friend"


async def test_age_is_validated(dp, bot, service):
    await _start_and_choose_lang(dp, bot, "ru")
    await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("Иван", chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("abc", chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("5", chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("200", chat_id=USER_ID)))

    # неправильный возраст не двигает анкету дальше
    user_texts = bot.session.texts_to(USER_ID)
    assert not any("Шаг 3/3" in t for t in user_texts), user_texts

    await dp.feed_update(bot, msg_update(message("18", chat_id=USER_ID)))
    user_texts = bot.session.texts_to(USER_ID)
    assert any("Шаг 3/3" in t for t in user_texts), user_texts


async def test_user_cancel_returns_to_services(dp, bot, service):
    """Раньше /cancel в личке не работал вообще — обработчика не было."""
    await _start_and_choose_lang(dp, bot, "ua")
    await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=USER_ID)))
    await dp.feed_update(bot, msg_update(message("/cancel", chat_id=USER_ID)))

    texts = bot.session.texts_to(USER_ID)
    assert any("скасовано" in t for t in texts), texts
    assert await crud.get_last_ticket_by_user(USER_ID) is None
