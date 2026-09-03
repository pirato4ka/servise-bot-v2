"""
FSM-состояния переживают рестарт бота.

В проде мастер услуги «ломала» связка из двух вещей: aiogram хранил состояния
в памяти, и рестарт бота между «Введи ID услуги» и самим вводом обнулял шаг —
дальнейший текст молча игнорировался. Здесь проверяем, что состояние лежит
в bot.db и читается новым экземпляром хранилища («рестартом»).
"""
from app.config import settings
from app.database import crud
from app.database.fsm_storage import SqliteFSMStorage
from tests.conftest import ADMIN_CHAT_ID, ADMIN_ID, cb_update, message, msg_update, user


async def test_storage_persists_across_instances(dp, bot):
    """Записанное одним инстансом читается другим (единый bot.db)."""
    from aiogram.fsm.storage.base import StorageKey

    s1 = SqliteFSMStorage(settings.DB_PATH)
    key = StorageKey(bot_id=bot.id, chat_id=ADMIN_CHAT_ID, user_id=ADMIN_ID)
    await s1.set_state(key, "AddService:id")
    await s1.set_data(key, {"id": "persisted"})

    # «после рестарта» — другой объект хранилища, тот же файл
    s2 = SqliteFSMStorage(settings.DB_PATH)
    assert await s2.get_state(key) == "AddService:id"
    assert await s2.get_data(key) == {"id": "persisted"}


async def test_admin_chat_wizard_survives_restart(dp, bot):
    """Рестарт между шагом ID и вводом не съедает мастер в админ-чате."""
    await crud.add_admin(ADMIN_ID)
    await dp.feed_update(bot, cb_update(
        "svc:add",
        message(chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID)),
        from_user=user(ADMIN_ID),
    ))

    # рестарт: новое хранилище поверх того же bot.db
    dp.fsm.storage = SqliteFSMStorage(settings.DB_PATH)

    texts_before = len(bot.session.texts_to(ADMIN_CHAT_ID))
    await dp.feed_update(bot, msg_update(message(
        "persist_id", chat_id=ADMIN_CHAT_ID, chat_type="supergroup", from_user=user(ADMIN_ID))))

    new_texts = bot.session.texts_to(ADMIN_CHAT_ID)[texts_before:]
    assert any("эмодзи" in t.lower() for t in new_texts), f"мастер умер после рестарта: {new_texts!r}"


async def test_private_wizard_survives_restart(dp, bot):
    """Рестарт не ломает мастер, запущенный админом в личке."""
    await crud.add_admin(ADMIN_ID)
    priv = ADMIN_ID
    await dp.feed_update(bot, msg_update(message(
        "/admin", chat_id=priv, from_user=user(ADMIN_ID))))
    await dp.feed_update(bot, cb_update("svc:add", message(
        chat_id=priv, from_user=user(ADMIN_ID)), from_user=user(ADMIN_ID)))

    # рестарт бота между приглашением ввести ID и самим вводом
    dp.fsm.storage = SqliteFSMStorage(settings.DB_PATH)

    texts_before = len(bot.session.texts_to(priv))
    await dp.feed_update(bot, msg_update(message(
        "persist_priv", chat_id=priv, from_user=user(ADMIN_ID))))

    new_texts = bot.session.texts_to(priv)[texts_before:]
    assert any("эмодзи" in t.lower() for t in new_texts), f"мастер в личке умер после рестарта: {new_texts!r}"
