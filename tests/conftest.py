"""Общая обвязка для тестов: временная БД, фейковая сессия Telegram, диспетчер."""
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from aiogram.client.default import Default
from aiogram.exceptions import TelegramBadRequest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP_DIR = tempfile.mkdtemp(prefix="bot-tests-")

os.environ["BOT_TOKEN"] = "123456789:AAA-fake-token-for-tests-0123456789"
os.environ["ADMIN_CHAT_ID"] = "-1001234567890"
os.environ["CRYPTO_BOT_TOKEN"] = "987654:AAA-fake-crypto-token-01234567890123"
os.environ["CRYPTO_BOT_IS_MAINNET"] = "False"
os.environ["DB_PATH"] = os.path.join(_TMP_DIR, "test.db")
os.environ["INVOICE_POLL_INTERVAL"] = "0"
os.environ["DEBUG_ALL"] = "False"

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.aiohttp import AiohttpSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.types import (  # noqa: E402
    Chat, Message, Update, User, CallbackQuery, ChatMemberAdministrator,
    ChatMemberMember, ChatMemberLeft,
)

from app.config import settings  # noqa: E402
from app.database.db import init_db  # noqa: E402
from app.bot import build_dispatcher  # noqa: E402

USER_ID = 555000111
ADMIN_ID = 777000222
ADMIN_CHAT_ID = settings.ADMIN_CHAT_ID


# Разрешённые Telegram HTML-теги (https://core.telegram.org/bots/api#html-style)
_ALLOWED_TAGS = re.compile(
    r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|tg-spoiler|blockquote"
    r"|span(?:\s+class=\"tg-spoiler\")?)\b[^>]*>"
)
_BAD_AMP = re.compile(r"&(?!(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);)")

MESSAGE_LIMIT = 4096
CAPTION_LIMIT = 1024


class TelegramValidationError(AssertionError):
    """То, что настоящий Telegram вернул бы как 400 Bad Request."""


class FakeSession(AiohttpSession):
    """
    Перехватывает все вызовы Telegram API и складывает их в self.calls.

    Заодно изображает строгость настоящего Telegram: проверяет HTML-разметку
    и лимиты длины. Без этого тесты «зелёные», а в проде сообщение теряется
    с ошибкой 400 — именно так в боте пропадали заявки клиентов.
    """

    def __init__(self):
        super().__init__()
        self.calls = []
        self.message_id = 1000
        self.chat_admins = []          # ответ get_chat_administrators
        self.chat_member_status = {}   # user_id -> status

    # ── валидация как у Telegram ──
    @staticmethod
    def _check_html(text: str, method_name: str) -> None:
        if not text:
            return
        plain = _ALLOWED_TAGS.sub("", text)
        if "<" in plain or ">" in plain:
            raise TelegramBadRequest(
                method=None,
                message=f"{method_name}: can't parse entities: unexpected '<' in {plain[:60]!r}",
            )
        if _BAD_AMP.search(plain):
            raise TelegramBadRequest(
                method=None,
                message=f"{method_name}: can't parse entities: bad '&'",
            )

    @staticmethod
    def _parse_mode(bot, method):
        """aiogram шлёт parse_mode как Default("parse_mode") — раскрываем в значение бота."""
        value = getattr(method, "parse_mode", None)
        if isinstance(value, Default):
            value = bot.default[value.name]
        return value

    @classmethod
    def _validate(cls, bot, method) -> None:
        name = type(method).__name__
        html_mode = cls._parse_mode(bot, method) == "HTML"

        text = getattr(method, "text", None)
        caption = getattr(method, "caption", None)

        if name == "SendMessage":
            if html_mode:
                cls._check_html(text, name)
            if text and len(text) > MESSAGE_LIMIT:
                raise TelegramBadRequest(method=None, message=f"{name}: message is too long")
        elif name in ("EditMessageText",):
            if html_mode:
                cls._check_html(text, name)
            if text and len(text) > MESSAGE_LIMIT:
                raise TelegramBadRequest(method=None, message=f"{name}: message is too long")
        elif name in ("SendPhoto", "SendDocument", "SendVoice", "SendAudio", "SendVideo", "SendAnimation"):
            if html_mode:
                cls._check_html(caption, name)
            if caption and len(caption) > CAPTION_LIMIT:
                raise TelegramBadRequest(method=None, message=f"{name}: caption is too long")
        elif name == "AnswerCallbackQuery":
            # Текст алерта показывается как есть, без разметки
            if text and len(text) > 200:
                raise TelegramBadRequest(method=None, message=f"{name}: text is too long")

    # ── helpers ──
    @property
    def sent(self):
        return [(type(m).__name__, m) for m in self.calls]

    def texts_to(self, chat_id):
        out = []
        for m in self.calls:
            chat = getattr(m, "chat_id", None)
            if chat != chat_id:
                continue
            text = getattr(m, "text", None) or getattr(m, "caption", None)
            if text:
                out.append(text)
        return out

    def all_texts(self):
        out = []
        for m in self.calls:
            text = getattr(m, "text", None) or getattr(m, "caption", None)
            if text:
                out.append(text)
        return out

    def clear(self):
        self.calls.clear()

    # ── Telegram API ──
    async def make_request(self, bot, method, timeout=None):
        self._validate(bot, method)
        self.calls.append(method)
        name = type(method).__name__

        if name in (
            "SendMessage", "SendPhoto", "SendDocument", "SendVoice", "SendVideo",
            "SendAudio", "SendAnimation", "SendVideoNote", "SendSticker",
        ):
            self.message_id += 1
            return self._message(method.chat_id, self.message_id, getattr(method, "text", None))

        if name == "GetMe":
            return User(id=123456789, is_bot=True, first_name="Test Bot", username="test_bot")

        if name == "GetChatAdministrators":
            return self.chat_admins

        if name == "GetChatMember":
            status = self.chat_member_status.get(method.user_id, "member")
            user = User(id=method.user_id, is_bot=False, first_name=f"User{method.user_id}")
            if status == "left":
                return ChatMemberLeft(user=user, status="left")
            return ChatMemberMember(user=user, status="member")

        if name in ("EditMessageReplyMarkup", "EditMessageText", "DeleteMessage", "DeleteWebhook"):
            return True

        return True

    @staticmethod
    def _message(chat_id, message_id, text=None):
        return Message(
            message_id=message_id,
            date=datetime.now(),
            chat=Chat(id=chat_id, type="private" if chat_id > 0 else "supergroup"),
            text=text,
        )

    async def close(self):
        pass


def make_bot() -> Bot:
    """Бот ровно как в проде: с parse_mode=HTML по умолчанию (см. app/bot.py)."""
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=FakeSession(),
    )


def user(id_: int = USER_ID, first_name: str = "Тест", username: str = "tester") -> User:
    return User(id=id_, is_bot=False, first_name=first_name, username=username)


def chat(chat_id: int, chat_type: str = "private") -> Chat:
    return Chat(id=chat_id, type=chat_type)


def message(
    text=None,
    chat_id: int = USER_ID,
    from_user: User = None,
    message_id: int = None,
    chat_type: str = "private",
    **kwargs,
) -> Message:
    return Message(
        message_id=message_id or _next_id(),
        date=datetime.now(),
        chat=chat(chat_id, chat_type),
        from_user=from_user or user(chat_id if chat_id > 0 else ADMIN_ID),
        text=text,
        **kwargs,
    )


_counter = {"value": 1}


def _next_id() -> int:
    _counter["value"] += 1
    return _counter["value"]


def msg_update(msg: Message) -> Update:
    return Update(update_id=_next_id(), message=msg)


def cb_update(data: str, msg: Message, from_user: User = None) -> Update:
    return Update(
        update_id=_next_id(),
        callback_query=CallbackQuery(
            id=str(_next_id()),
            from_user=from_user or user(),
            chat_instance="1",
            data=data,
            message=msg,
        ),
    )


def admin_member(uid: int, first_name: str = "Admin") -> ChatMemberAdministrator:
    return ChatMemberAdministrator(
        user=User(id=uid, is_bot=False, first_name=first_name),
        status="administrator",
        is_anonymous=False,
        can_be_edited=False,
        can_manage_chat=True,
        can_delete_messages=True,
        can_manage_video_chats=True,
        can_restrict_members=True,
        can_promote_members=False,
        can_change_info=True,
        can_invite_users=True,
        can_post_messages=True,
        can_edit_messages=True,
        can_pin_messages=True,
        can_post_stories=True,
        can_edit_stories=True,
        can_delete_stories=True,
        can_manage_topics=True,
    )


@pytest.fixture(autouse=True)
async def fresh_db():
    """Каждый тест стартует с чистой базой."""
    path = Path(settings.DB_PATH)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    await init_db()
    yield
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()


@pytest.fixture()
def bot():
    return make_bot()


@pytest.fixture(scope="session")
def dp():
    """Роутеры — синглтоны уровня модуля, поэтому диспетчер создаём один раз на прогон."""
    return build_dispatcher()


@pytest.fixture(autouse=True)
def _reset_throttling():
    """Счётчики антифлуда общие на процесс — между тестами их обнуляем."""
    from app.handlers.user_chat import throttling

    throttling.reset()
    yield
    throttling.reset()


@pytest.fixture(autouse=True)
def _reset_fsm(dp):
    """Сбрасываем FSM-состояния между тестами (storage общий на весь прогон)."""
    dp.storage.storage.clear()
    yield
    dp.storage.storage.clear()


@pytest.fixture()
async def service():
    """Создаёт активную услугу, с которой работает пользователь."""
    from app.database import crud
    await crud.create_service({
        "id": "test_service",
        "emoji": "🔒",
        "title_ua": "Тестова послуга",
        "title_ru": "Тестовая услуга",
        "button_label_ua": "🔒 Тестова послуга",
        "button_label_ru": "🔒 Тестовая услуга",
        "short_desc_ua": "Опис тестової послуги",
        "short_desc_ru": "Описание тестовой услуги",
        "terms_ua": "Умови тестової послуги",
        "terms_ru": "Условия тестовой услуги",
    })
    return await crud.get_service_by_id("test_service")
