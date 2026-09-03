"""
Определение рабочего пути к SQLite.

На хостингах (bothost и подобные) каталог с базой часто примонтирован от root,
а бот работает под непривилегированным пользователем — тогда SQLite падает с
«unable to open database file». Чтобы бот стартовал в любом случае, пробуем
каталоги по очереди и берём первый пригодный для записи.
"""
import logging
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

DB_FILENAME = "bot.db"
_resolved_path = None


def _is_usable(path: Path) -> bool:
    """Проверяет, что каталог существует, а файл базы реально создаётся и пишется."""
    directory = path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.debug(f"DB bootstrap: не удалось создать {directory}: {e}")
        return False

    for attempt in (1, 2):
        try:
            probe = directory / f".write-test-{os.getpid()}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as e:
            if attempt == 1 and _try_relax_permissions(directory):
                continue
            log.debug(f"DB bootstrap: каталог {directory} недоступен для записи: {e}")
            return False

        try:
            conn = sqlite3.connect(str(path), timeout=5.0)
            try:
                conn.execute("CREATE TABLE IF NOT EXISTS _bootstrap_check (i INTEGER)")
                conn.execute("DROP TABLE _bootstrap_check")
                conn.commit()
            finally:
                conn.close()
            return True
        except sqlite3.Error as e:
            log.debug(f"DB bootstrap: SQLite не смог открыть {path}: {e}")
            return False
    return False


def _try_relax_permissions(directory: Path) -> bool:
    """Если мы root — отдаём каталог текущему пользователю. Иначе ничего не делаем."""
    if os.geteuid() != 0:
        return False
    try:
        os.chmod(directory, 0o777)
        log.warning(f"DB bootstrap: расширены права на {directory} (0777), чтобы бот мог писать базу")
        return True
    except OSError:
        return False


def candidate_paths(configured: str) -> List[Path]:
    """Список путей, которые пробуем по очереди."""
    paths = [Path(configured).expanduser()]
    cwd = Path.cwd()
    for extra in (cwd / "data" / DB_FILENAME, cwd / DB_FILENAME):
        if str(extra) != str(paths[0]):
            paths.append(extra)
    tmp = Path(tempfile.gettempdir()) / DB_FILENAME
    if str(tmp) not in {str(p) for p in paths}:
        paths.append(tmp)
    return paths


def resolve_db_path() -> str:
    """
    Возвращает первый путь, куда реально можно писать, и прописывает его в settings.
    Результат кешируется, чтобы не проверять каталоги на каждом запросе.
    """
    global _resolved_path
    if _resolved_path:
        return _resolved_path

    configured = str(settings_value())
    tried = []
    for path in candidate_paths(configured):
        tried.append(str(path))
        if _is_usable(path):
            _resolved_path = str(path)
            if _resolved_path != configured:
                log.warning(
                    "⚠️  БД недоступна по пути %s — пишем в %s. "
                    "Проверьте права на каталог или монтирование тома, иначе данные "
                    "могут не сохраниться между перезапусками.",
                    configured, _resolved_path,
                )
            else:
                log.info(f"База данных: {_resolved_path}")
            return _resolved_path

    raise RuntimeError(
        "Не удалось найти каталог, доступный для записи под базу данных. "
        f"Пробовали: {', '.join(tried)}. "
        "Укажите DB_PATH в .env (например /app/data/bot.db) и проверьте права на каталог."
    )


def settings_value() -> str:
    from app.config import settings
    return settings.DB_PATH


def apply_resolved_path():
    """Записывает найденный путь обратно в настройки, чтобы get_db() использовал его."""
    from app.config import settings
    resolved = resolve_db_path()
    if settings.DB_PATH != resolved:
        settings.DB_PATH = resolved
    return resolved


def reset_cache():
    """Сброс кеша — используется в тестах."""
    global _resolved_path
    _resolved_path = None
