"""Разбор callback_data, устойчивый к «неудобным» аргументам."""


def cb_args(data: str, prefix: str, tail: int = 0) -> tuple[str, ...]:
    """
    Разбирает ``callback_data`` вида ``prefix:arg:arg2``.

    ``tail`` — сколько последних сегментов считать отдельными аргументами
    (язык, имя поля); всё, что перед ними, склеивается обратно в одно значение.
    Так ID услуги, в котором случайно оказалось двоеточие, не ломает парсинг:
    ``svc:editfield:vip:gold:ua:title`` -> ``("vip:gold", "ua", "title")``.

    Возвращает ``tail + 1`` строк; при нехватке сегментов — пустые строки,
    чтобы вызывающий код мог спокойно проверить результат.
    """
    rest = data[len(prefix):] if data.startswith(prefix) else data
    if tail <= 0:
        return (rest,)

    parts = rest.rsplit(":", tail)
    if len(parts) < tail + 1:
        return ("",) * (tail + 1)
    return (":".join(parts[:-tail]), *parts[-tail:])
