"""Мелкие утилиты: даты, трафик, генерация имён."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str | None) -> datetime | None:
    """Парсит дату из API Remnawave ('2025-01-01T00:00:00.000Z' и т.п.)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def to_iso(dt: datetime) -> str:
    """Форматирует дату для API Remnawave: 2025-01-01T00:00:00.000Z"""
    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="milliseconds") + "Z"


def fmt_date(dt: datetime | None, tz) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(tz).strftime("%d.%m.%Y %H:%M")


def fmt_bytes(num: int | float | None) -> str:
    if num is None:
        return "—"
    num = float(num)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ", "ПБ"):
        if abs(num) < 1024 or unit == "ПБ":
            if unit == "Б":
                return f"{int(num)} {unit}"
            return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} ПБ"


def human_days_left(expire_at: datetime | None) -> int | None:
    if expire_at is None:
        return None
    delta = expire_at - utcnow()
    return max(0, int(delta.total_seconds() // 86400) + (1 if delta.total_seconds() % 86400 else 0))


def unique_username(base: str) -> str:
    """Имя пользователя Remnawave: без пробелов, a-zA-Z0-9-_ , 3-36 символов."""
    base = "".join(ch for ch in base if ch.isalnum() or ch in "-_")
    return base[:28]


def random_suffix() -> str:
    return secrets.token_hex(2)
