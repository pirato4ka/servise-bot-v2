"""
Антифлуд для свободных сообщений пользователя.

Документация обещала «Антифлуд для юзеров», а пакет ``app/middlewares`` был
пустым. Между тем каждое свободное сообщение клиента ``user_chat`` пересылает
в админ-чат — то есть один тролль способен завалить рабочую ленту админов.

Ограничение сознательно мягкое и точечное:

* вешается только на ``user_chat.router`` — анкета, кнопки услуг и админ-чат
  не затрагиваются, FSM-диалог порвать нельзя;
* админы не ограничиваются;
* при превышении клиенту один раз за окно приходит внятная просьба подождать,
  а не молчаливый игнор: человек должен понимать, что сообщение не ушло.
"""
import logging
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.config import settings
from app.database import crud
from app.data.texts import t

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """Считает сообщения пользователя в скользящем окне."""

    def __init__(self, limit: int = 5, window: float = 10.0, max_tracked_users: int = 10_000):
        self.limit = limit
        self.window = window
        self.max_tracked_users = max_tracked_users
        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._last_warned: dict[int, float] = {}

    def _prune(self, user_id: int, now: float) -> deque[float]:
        hits = self._hits[user_id]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        return hits

    def _forget_stale(self, now: float) -> None:
        """
        Не держим память о тех, кто давно не писал.

        Жёсткий потолок по числу отслеживаемых пользователей: иначе волна
        сообщений от тысяч разных аккаунтов растянула бы словарь до размера трафика.
        """
        if len(self._hits) <= self.max_tracked_users:
            return

        for uid, hits in list(self._hits.items()):
            if not hits or now - hits[-1] > self.window:
                self._hits.pop(uid, None)
                self._last_warned.pop(uid, None)

        overflow = len(self._hits) - self.max_tracked_users
        if overflow > 0:
            oldest = sorted(self._hits.items(), key=lambda item: item[1][-1] if item[1] else 0.0)
            for uid, _ in oldest[:overflow]:
                self._hits.pop(uid, None)
                self._last_warned.pop(uid, None)

    def reset(self) -> None:
        """Сброс счётчиков (используется в тестах между кейсами)."""
        self._hits.clear()
        self._last_warned.clear()

    def allow(self, user_id: int, now: float | None = None) -> bool:
        """Основная проверка — вынесена из async, чтобы её можно было тестировать."""
        now = time.monotonic() if now is None else now
        hits = self._prune(user_id, now)
        hits.append(now)
        self._forget_stale(now)
        return len(hits) <= self.limit

    def should_warn(self, user_id: int, now: float) -> bool:
        """Предупреждаем не чаще раза в окно — иначе бот сам превратится во флуд."""
        last = self._last_warned.get(user_id)
        if last is not None and now - last < self.window:
            return False
        self._last_warned[user_id] = now
        return True

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.from_user is None:
            return await handler(event, data)

        user_id = event.from_user.id
        if event.chat.id == settings.ADMIN_CHAT_ID or await crud.is_admin(user_id):
            return await handler(event, data)

        now = time.monotonic()
        if self.allow(user_id, now):
            return await handler(event, data)

        if self.should_warn(user_id, now):
            logger.info(f"THROTTLING: user={user_id} превысил {self.limit} сообщений за {self.window}с")
            try:
                lang = await crud.get_user_lang(user_id)
                await event.bot.send_message(chat_id=event.chat.id, text=t("flood_warning", lang))
            except Exception as e:  # noqa: BLE001 - предупреждение не критично
                logger.warning(f"THROTTLING: не удалось предупредить {user_id}: {e}")
        return None
