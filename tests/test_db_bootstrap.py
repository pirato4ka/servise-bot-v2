"""Переносимость пути к базе: бот должен стартовать даже с недоступным каталогом."""
import os
import stat
from pathlib import Path

import pytest

from app.config import settings
from app.database import bootstrap


@pytest.fixture()
def _restore_db_path():
    original = settings.DB_PATH
    bootstrap.reset_cache()
    yield
    settings.DB_PATH = original
    bootstrap.reset_cache()


async def test_creates_missing_directory(_restore_db_path, tmp_path):
    """Каталог указан, но не существует — создаём его сами."""
    target = tmp_path / "nested" / "deeper" / "bot.db"
    settings.DB_PATH = str(target)

    resolved = bootstrap.apply_resolved_path()

    assert resolved == str(target)
    assert Path(resolved).parent.exists()


async def test_falls_back_when_directory_not_writable(_restore_db_path, tmp_path, monkeypatch, caplog):
    """Каталог есть, но писать нельзя (том от root) — уходим в запасной путь."""
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x: писать нельзя
    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 1000)  # не root — chmod не поможет

    writable = tmp_path / "writable"
    writable.mkdir()
    monkeypatch.chdir(writable)

    settings.DB_PATH = str(blocked / "bot.db")

    resolved = bootstrap.apply_resolved_path()

    assert resolved != str(blocked / "bot.db")
    assert Path(resolved).parent == writable / "data"
    assert settings.DB_PATH == resolved
    assert Path(resolved).exists(), "файл базы должен быть создан"


async def test_root_relaxes_permissions(_restore_db_path, tmp_path, monkeypatch):
    """Под root бот сам открывает права на каталог и остаётся на заданном пути."""
    if os.geteuid() != 0:
        pytest.skip("нужны права root")

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o700)
    settings.DB_PATH = str(blocked / "bot.db")

    resolved = bootstrap.apply_resolved_path()

    assert resolved == str(blocked / "bot.db")


async def test_init_db_uses_resolved_path(_restore_db_path, tmp_path, monkeypatch):
    """init_db() поднимает схему даже если изначальный путь недоступен."""
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(stat.S_IRUSR | stat.S_IXUSR)
    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 1000)
    monkeypatch.chdir(tmp_path)

    settings.DB_PATH = str(blocked / "bot.db")

    from app.database.db import init_db
    from app.database import crud

    await init_db()
    await crud.upsert_user(1, "tester", "Tester")
    assert await crud.get_users_count() == 1

    import sqlite3
    conn = sqlite3.connect(settings.DB_PATH)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "services" in tables and "admins" in tables
