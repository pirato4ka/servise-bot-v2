"""
Утилиты подготовки текста для Telegram.

Бот работает с ``parse_mode=HTML`` (см. ``app/bot.py``), поэтому ЛЮБОЙ
пользовательский текст, попадающий в шаблон, обязан быть экранирован:
одна амперсанда или угловая скобка в имени клиента — и Telegram отвечает
``400 Bad Request: can't parse entities``, а сообщение теряется целиком.

Второй класс проблем — лимиты Telegram: 4096 символов в сообщении,
1024 в подписи к медиа, 64 в тексте кнопки. Их нарушение тоже даёт 400.
"""
import html
import re
from typing import Any

MESSAGE_LIMIT = 4096
CAPTION_LIMIT = 1024
BUTTON_LIMIT = 64
ELLIPSIS = "…"

_TAG_RE = re.compile(r"<[^>]*>")

# Символы, которые «приклеиваются» к предыдущему эмодзи: вариационные
# селекторы, ZWJ, тон кожи, региональные индикаторы, keycap, теги.
_COMBINING = frozenset({0x200D, 0xFE0E, 0xFE0F, 0x20E3})


def esc(value: Any) -> str:
    """Экранирует ``&``, ``<``, ``>`` для parse_mode=HTML. None -> ''."""
    if value is None:
        return ""
    return html.escape(str(value), quote=False)


def strip_tags(value: Any) -> str:
    """Убирает HTML-разметку, оставляя читаемый текст (для превью/логов)."""
    if not value:
        return ""
    return _TAG_RE.sub("", str(value)).strip()


def truncate(value: Any, limit: int) -> str:
    """Обрезает строку до ``limit`` символов, добавляя многоточие."""
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1].rstrip() + ELLIPSIS


def fit(template: str, limit: int, **values: Any) -> str:
    """
    Подставляет значения в шаблон и гарантирует, что результат влезет в лимит.

    Ужимает самые длинные значения (обычно это текст сообщения), а не рубит
    готовую строку пополам — так не теряется вёрстка шаблона.
    Значения должны быть уже экранированы там, где это нужно (см. ``esc``).
    """
    # Без значений template.format() трогать нельзя: в тексте сообщения могут
    # встречаться фигурные скобки («{0}»), и format() на них упадёт.
    text = template.format(**values) if values else str(template)
    if len(text) <= limit:
        return text

    keys = sorted(values, key=lambda k: -len(str(values[k] or "")))
    for key in keys:
        current = str(values[key] or "")
        if not current:
            continue
        overflow = len(text) - limit
        values[key] = truncate(current, max(0, len(current) - overflow))
        text = template.format(**values)
        if len(text) <= limit:
            return text

    return truncate(text, limit)


def format_amount(value: Any) -> str:
    """100.0 -> '100', 0.05000000 -> '0.05'. Крипта — до 8 знаков."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    return f"{number:.8f}".rstrip("0").rstrip(".")


def first_emoji(value: Any, max_clusters: int = 2) -> str:
    """
    Берёт первые эмодзи из строки, не разрезая их по кодовым точкам.

    Прежний ``text[:2]`` кромсал составные эмодзи (👨‍👩‍👦, 🇺🇦, 🛡️)
    пополам, и в интерфейсе появлялись «квадратики».
    """
    if not value:
        return ""
    text = str(value)
    result: list[str] = []
    i, n = 0, len(text)

    # Ведущие пробелы пропускаем, но после первого эмодзи пробел — это граница:
    # иначе в «🛡️ Безпечна угода» вторым «кластером» становилась буква «Б».
    while i < n and text[i].isspace():
        i += 1

    while i < n and len(result) < max_clusters:
        char = text[i]
        if char.isspace():
            break
        cluster = char
        i += 1
        while i < n:
            code = ord(text[i])
            is_regional = 0x1F1E6 <= code <= 0x1F1FF
            is_skin_tone = 0x1F3FB <= code <= 0x1F3FF
            is_tag = 0xE0020 <= code <= 0xE007F
            if not (code in _COMBINING or is_regional or is_skin_tone or is_tag):
                break
            cluster += text[i]
            i += 1
            if code == 0x200D and i < n:  # ZWJ склеивает со следующим символом
                cluster += text[i]
                i += 1
        result.append(cluster)

    return "".join(result)
