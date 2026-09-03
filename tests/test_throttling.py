"""
Антифлуд для свободных сообщений пользователя.

Каждое свободное сообщение клиента бот пересылает в админ-чат, поэтому поток
от одного пользователя ограничен middleware'ом на user_chat.router.
Проверяем, что ограничение мягкое: анкета, админы и спокойный диалог не страдают.
"""
from app.database import crud
from app.handlers.user_chat import throttling
from app.middlewares.throttling import ThrottlingMiddleware
from tests.conftest import ADMIN_CHAT_ID, ADMIN_ID, USER_ID, cb_update, message, msg_update, user

CONTINUATION = "Продолжение диалога"
FLOOD_HINT = "Надто багато повідомлень"


async def _client_with_ticket(chat_id: int = USER_ID):
    await crud.upsert_user(chat_id, "tester", "Тест")
    await crud.update_user_questionnaire(chat_id, "Иван", 25, "me", "test_service")
    await crud.create_ticket(chat_id, 7001, ADMIN_CHAT_ID, "test_service")


def test_allow_respects_limit_and_window():
    mw = ThrottlingMiddleware(limit=3, window=1.0)
    now = 100.0
    assert [mw.allow(1, now + i * 0.01) for i in range(4)] == [True, True, True, False]
    assert mw.allow(1, now + 1.5) is True, "после окна счётчик должен обнуляться"


def test_tracked_users_are_bounded():
    mw = ThrottlingMiddleware(limit=5, window=60.0, max_tracked_users=10)
    now = 1000.0
    for uid in range(500):
        mw.allow(uid, now + uid * 0.001)
    assert len(mw._hits) <= 10, f" middleware держит {len(mw._hits)} пользователей"


async def test_flood_is_stopped_and_user_warned(dp, bot, service):
    await _client_with_ticket()

    for i in range(12):
        await dp.feed_update(bot, msg_update(message(f"сообщение {i}", chat_id=USER_ID,
                                                     from_user=user(USER_ID))))

    forwarded = [t for t in bot.session.texts_to(ADMIN_CHAT_ID) if CONTINUATION in t]
    assert 0 < len(forwarded) < 12, f"антифлуд не сработал: {len(forwarded)} сообщений"
    assert any(FLOOD_HINT in t for t in bot.session.texts_to(USER_ID)), bot.session.texts_to(USER_ID)


async def test_flood_warning_sent_once_per_window(dp, bot, service):
    """Предупреждение не должно само превращаться во флуд."""
    await _client_with_ticket()

    for i in range(20):
        await dp.feed_update(bot, msg_update(message(f"спам {i}", chat_id=USER_ID, from_user=user(USER_ID))))

    warnings = [t for t in bot.session.texts_to(USER_ID) if FLOOD_HINT in t]
    assert len(warnings) == 1, warnings


async def test_admin_is_not_throttled(dp, bot, service):
    await crud.add_admin(ADMIN_ID)
    await _client_with_ticket(ADMIN_ID)

    for i in range(12):
        await dp.feed_update(bot, msg_update(message(f"служебное {i}", chat_id=ADMIN_ID,
                                                     from_user=user(ADMIN_ID))))

    forwarded = [t for t in bot.session.texts_to(ADMIN_CHAT_ID) if CONTINUATION in t]
    assert len(forwarded) == 12, f"админ ограничен антифлудом: {len(forwarded)}"
    assert not any(FLOOD_HINT in t for t in bot.session.texts_to(ADMIN_ID))


async def test_questionnaire_is_not_throttled(dp, bot, service):
    """Анкета идёт в другом роутере: быстрый ввод не должен её рвать."""
    await dp.feed_update(bot, msg_update(message("/start", chat_id=USER_ID, from_user=user(USER_ID))))
    await dp.feed_update(bot, cb_update("lang:ua", message(chat_id=USER_ID), from_user=user(USER_ID)))

    for _ in range(10):  # ошибочные ответы один за другим
        await dp.feed_update(bot, cb_update("agree:test_service", message(chat_id=USER_ID),
                                            from_user=user(USER_ID)))
        await dp.feed_update(bot, msg_update(message("Иван", chat_id=USER_ID, from_user=user(USER_ID))))
        await dp.feed_update(bot, msg_update(message("25", chat_id=USER_ID, from_user=user(USER_ID))))
        await dp.feed_update(bot, msg_update(message("не разобрал", chat_id=USER_ID, from_user=user(USER_ID))))

    texts = bot.session.texts_to(USER_ID)
    assert any("Крок 3/3" in t for t in texts), texts[-3:]
    assert not any(FLOOD_HINT in t for t in texts), "анкету порвал антифлуд"


async def test_calm_dialogue_is_not_affected(dp, bot, service):
    """Обычная переписка (реже лимита) доходит целиком."""
    await _client_with_ticket()
    mw_limit = throttling.limit

    for i in range(mw_limit):
        await dp.feed_update(bot, msg_update(message(f"вопрос {i}", chat_id=USER_ID, from_user=user(USER_ID))))

    forwarded = [t for t in bot.session.texts_to(ADMIN_CHAT_ID) if CONTINUATION in t]
    assert len(forwarded) == mw_limit, forwarded
    assert not any(FLOOD_HINT in t for t in bot.session.texts_to(USER_ID))
