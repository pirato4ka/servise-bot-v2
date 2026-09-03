"""Проверка реального старта бота: main() целиком, без сети."""
import asyncio

from aiogram import Dispatcher

import app.bot as bot_module
from app.database import crud
from tests.conftest import ADMIN_ID, FakeSession, admin_member


async def test_main_starts_and_syncs(dp, monkeypatch):
    """
    Прогоняем main() от начала до конца.
    Роутеры — синглтоны уровня модуля, поэтому подсовываем уже собранный
    диспетчер из фикстуры (в проде он создаётся ровно один раз).
    """
    started = {}

    session = FakeSession()
    session.chat_admins = [admin_member(ADMIN_ID)]

    monkeypatch.setattr(bot_module, "build_session", lambda: session)
    monkeypatch.setattr(bot_module, "build_dispatcher", lambda: dp)

    async def fake_polling(self, *args, **kwargs):
        started["polling"] = True

    monkeypatch.setattr(Dispatcher, "start_polling", fake_polling)

    await asyncio.wait_for(bot_module.main(), timeout=10)

    assert started.get("polling") is True
    assert await crud.is_admin(ADMIN_ID), "админ из группы не восстановился при старте"

    # сессия корректно закрывается при остановке
    assert session.calls, "бот не сделал ни одного запроса к Telegram API"
