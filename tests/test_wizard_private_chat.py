"""
Регрессия: мастер добавления/правки услуги из ЛИЧКИ админа молча глотал ввод.

Админ может открыть админ-панель в личке (/admin разрешён админам в любом
чате), нажать «🆕 Добавить услугу» и получить «Введи ID услуги». Раньше ввод
ID в личке молча проглатывался: обработчики шагов мастера фильтровались строго
по админ-чату, а user_chat.user_free_message принимал текст за сообщение
пользователя во время анкеты (state не None) и выходил без ответа.
"""
from app.database import crud
from tests.conftest import ADMIN_ID, cb_update, message, msg_update, user

PRIVATE_ADMIN_CHAT = ADMIN_ID  # в личке chat.id == user.id


async def _make_admin():
    """В проде GLS-админ синхронизируется при старте; в тесте добавляем вручную."""
    await crud.add_admin(ADMIN_ID)


async def _start_wizard_in_private(dp, bot):
    """/admin в личке → панель → «Управление услугами» → 🆕 (svc:add)."""
    await _make_admin()
    await dp.feed_update(bot, msg_update(message(
        "/admin", chat_id=PRIVATE_ADMIN_CHAT, from_user=user(ADMIN_ID))))
    await dp.feed_update(bot, cb_update("admin:services", message(
        chat_id=PRIVATE_ADMIN_CHAT, from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))
    await dp.feed_update(bot, cb_update("svc:add", message(
        chat_id=PRIVATE_ADMIN_CHAT, from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))


async def test_admin_adds_service_from_private_chat(dp, bot):
    """Полный прогон мастера в личке: ввод ID не должен проглатываться."""
    await _start_wizard_in_private(dp, bot)

    texts_before = len(bot.session.texts_to(PRIVATE_ADMIN_CHAT))
    await dp.feed_update(bot, msg_update(message(
        "confidential_docs", chat_id=PRIVATE_ADMIN_CHAT, from_user=user(ADMIN_ID))))

    # Ожидаем следующий вопрос мастера (эмодзи), а не тишину
    new_texts = bot.session.texts_to(PRIVATE_ADMIN_CHAT)[texts_before:]
    assert any("эмодзи" in t.lower() for t in new_texts), f"мастер не сдвинулся: {new_texts!r}"


async def test_private_admin_wizard_does_not_create_service_yet(dp, bot):
    """На шаге ID услуга ещё не создаётся (это лишь первый шаг мастера)."""
    await _start_wizard_in_private(dp, bot)
    await dp.feed_update(bot, msg_update(message(
        "confidential_docs", chat_id=PRIVATE_ADMIN_CHAT, from_user=user(ADMIN_ID))))
    assert await crud.get_service_by_id("confidential_docs") is None


async def test_private_wizard_full_run_creates_service(dp, bot):
    """Мастер из лички проходит все 10 шагов и создаёт услугу."""
    await _start_wizard_in_private(dp, bot)
    steps = [
        "confidential_docs", "🔒",
        "Конфіденційні документи", "Конфиденциальные документы",
        "Короткий опис UA", "Краткое описание RU",
        "Умови UA", "Условия RU",
        "🔒 Конфіденційні документи", "🔒 Конфиденциальные документы",
    ]
    for step in steps:
        await dp.feed_update(bot, msg_update(message(
            step, chat_id=PRIVATE_ADMIN_CHAT, from_user=user(ADMIN_ID))))

    svc = await crud.get_service_by_id("confidential_docs")
    assert svc is not None, "услуга не создана"
    assert svc["title_ru"] == "Конфиденциальные документы"
    assert svc["button_label_ua"] == "🔒 Конфіденційні документи"
