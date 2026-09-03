"""
Персистентное FSM-хранилище на aiosqlite.

Зачем: aiogram по умолчанию хранит состояния FSM в памяти (MemoryStorage) и
теряет их при каждом рестарте бота. На практике это выглядело как «мастер
добавления услуги не работает»: админ нажал «🆕 Добавить услугу», получил
«Введи ID услуги», бота перезапустили (деплой/правка .env), и после этого любой
ввод молча уходил в никуда — состояние AddService.id уже было стёрто, а до
обработчиков мастера сообщение не доходило.

Хранилище держит данные в таблице ``fsm_states`` того же ``bot.db``, что и
остальные данные. Ключ — StorageKey aiogram (bot_id, chat_id, user_id,
thread_id, business_connection_id, destiny). NULL-поля ключа кодируются
нейтральными значениями (0 / ''), потому что в SQLite NULL в составном ключе
не равен самому себе и дубликаты строк разъехались бы.

Соединение открывается на каждую операцию (как и в ``crud``): так хранилище
переживает удаление/пересоздание файла БД (это делает обвязка тестов между
кейсами) и не держит устаревший файловый дескриптор после рестарта.
"""
import json
import logging
from typing import Any, Dict, Optional

import aiosqlite

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

logger = logging.getLogger(__name__)

# Колонки ключа, которые в aiogram могут быть None (thread_id,
# business_connection_id), в SQLite кодируем нейтрально — иначе NULL-значения
# в PRIMARY KEY считаются разными и upsert плодил бы дубликаты строк.
_NULL_THREAD = 0
_NULL_BUSINESS = ""

# «Значение не передавали» — отличается от явного None (сброс через clear()).
_UNSET = object()


class SqliteFSMStorage(BaseStorage):
    """Хранит состояние и данные FSM в таблице SQLite (переживает рестарт бота)."""

    def __init__(self, db_path: str, table: str = "fsm_states") -> None:
        self.db_path = db_path
        self.table = table

    # ── служебное ────────────────────────────────────────────────

    async def _connect(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path, timeout=15.0)
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute("PRAGMA synchronous=NORMAL")
        return db

    async def _ensure_schema(self, db: aiosqlite.Connection) -> None:
        """Гарантирует наличие таблицы (идиоматично: CREATE IF NOT EXISTS).

        Выполняется на каждой операции без кэша: файл БД может быть удалён и
        пересоздан между вызовами (так делают тесты, а в проде бывает ручная
        замена bot.db), поэтому полагаться на однократное создание нельзя.
        """
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                bot_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                thread_id INTEGER NOT NULL DEFAULT {_NULL_THREAD},
                business_connection_id TEXT NOT NULL DEFAULT '{_NULL_BUSINESS}',
                destiny TEXT NOT NULL DEFAULT 'default',
                state TEXT,
                data TEXT NOT NULL DEFAULT '{{}}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (bot_id, chat_id, user_id, thread_id,
                             business_connection_id, destiny)
            )
        """)
        await db.commit()

    @staticmethod
    def _values(key: StorageKey) -> tuple:
        """StorageKey -> значения WHERE/INSERT (SQLite-совместимые)."""
        return (
            key.bot_id,
            key.chat_id,
            key.user_id,
            key.thread_id if key.thread_id is not None else _NULL_THREAD,
            key.business_connection_id if key.business_connection_id is not None else _NULL_BUSINESS,
            key.destiny,
        )

    @staticmethod
    def _where(table: str) -> str:
        return (
            "bot_id=? AND chat_id=? AND user_id=? AND thread_id=? "
            "AND business_connection_id=? AND destiny=? "
        )

    async def _upsert(self, key: StorageKey, *, state: Any = _UNSET,
                      data: Any = _UNSET) -> None:
        """
        Вставляет или обновляет строку ключа.

        state/data со значением _UNSET не трогают свою колонку: set_data не
        затирает состояние мастера, set_state — данные. Явный None (clear())
        записывается как NULL.
        """
        db = await self._connect()
        try:
            await self._ensure_schema(db)
            key_cols = (
                "bot_id, chat_id, user_id, thread_id, "
                "business_connection_id, destiny"
            )
            cols = self._values(key)
            conflict = (
                "ON CONFLICT(bot_id, chat_id, user_id, thread_id, "
                "business_connection_id, destiny)"
            )

            if state is not _UNSET and data is not _UNSET:
                state_sql = state.state if isinstance(state, State) else state
                data_sql = json.dumps(data, ensure_ascii=False, default=str)
                sql = (
                    f"INSERT INTO {self.table} ({key_cols}, state, data) "
                    f"VALUES (?,?,?,?,?,?,?,?) {conflict} "
                    f"DO UPDATE SET state=excluded.state, data=excluded.data"
                )
                params = (*cols, state_sql, data_sql)
            elif state is not _UNSET:
                state_sql = state.state if isinstance(state, State) else state
                sql = (
                    f"INSERT INTO {self.table} ({key_cols}, state) "
                    f"VALUES (?,?,?,?,?,?,?) {conflict} "
                    f"DO UPDATE SET state=excluded.state"
                )
                params = (*cols, state_sql)
            else:  # только данные
                data_sql = json.dumps(data, ensure_ascii=False, default=str)
                sql = (
                    f"INSERT INTO {self.table} ({key_cols}, data) "
                    f"VALUES (?,?,?,?,?,?,?) {conflict} "
                    f"DO UPDATE SET data=excluded.data"
                )
                params = (*cols, data_sql)
            await db.execute(sql, params)
            await db.commit()
        finally:
            await db.close()

    # ── API BaseStorage ──────────────────────────────────────────

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await self._upsert(key, state=state)

    async def get_state(self, key: StorageKey) -> Optional[str]:
        db = await self._connect()
        try:
            await self._ensure_schema(db)
            async with db.execute(
                f"SELECT state FROM {self.table} WHERE {self._where(self.table)}",
                self._values(key),
            ) as cur:
                row = await cur.fetchone()
            return row[0] if row else None
        finally:
            await db.close()

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        await self._upsert(key, data=data)

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        db = await self._connect()
        try:
            await self._ensure_schema(db)
            async with db.execute(
                f"SELECT data FROM {self.table} WHERE {self._where(self.table)}",
                self._values(key),
            ) as cur:
                row = await cur.fetchone()
            if not row or not row[0]:
                return {}
            try:
                value = json.loads(row[0])
            except (TypeError, ValueError):
                logger.warning("FSM: повреждён JSON данных для %s — сбрасываю", key)
                return {}
            return value if isinstance(value, dict) else {}
        finally:
            await db.close()

    async def close(self) -> None:
        """Соединения открываются на операцию, закрывать нечего."""

    async def clear_all(self) -> None:
        """Полная очистка (используется тестами между кейсами)."""
        db = await self._connect()
        try:
            await self._ensure_schema(db)
            await db.execute(f"DELETE FROM {self.table}")
            await db.commit()
        finally:
            await db.close()
