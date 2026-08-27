"""Конфигурация бота: читает .env, валидирует, собирает тарифы."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class ConfigError(Exception):
    """Ошибка конфигурации (показывается администратору в понятном виде)."""


def _get(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


def _get_bool(name: str, default: bool = False) -> bool:
    raw = _get(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on", "y"}


@dataclass(frozen=True)
class Tariff:
    id: str
    title: str
    days: int
    description: str
    price_rub: float | None = None
    price_stars: int | None = None
    price_usdt: float | None = None

    def price_line(self) -> str:
        parts: list[str] = []
        if self.price_rub:
            parts.append(f"{self.price_rub:g} ₽")
        if self.price_stars:
            parts.append(f"{self.price_stars:g} ⭐")
        if self.price_usdt:
            parts.append(f"{self.price_usdt:g} USDT")
        return " / ".join(parts) if parts else "цена не задана"


@dataclass
class Config:
    bot_token: str
    admin_ids: tuple[int, ...]
    panel_url: str
    api_token: str
    api_prefix: str
    sub_page_domain: str | None
    squad_uuid: str | None
    reset_traffic_on_renew: bool
    cryptobot_token: str | None
    cryptobot_testnet: bool
    yookassa_shop_id: str | None
    yookassa_secret: str | None
    db_path: str
    tz: ZoneInfo
    support_url: str | None
    tariffs: dict[str, Tariff]

    # ── провайдеры оплаты, доступные с текущими настройками ──
    @property
    def stars_enabled(self) -> bool:
        return any(t.price_stars for t in self.tariffs.values())

    @property
    def cryptobot_enabled(self) -> bool:
        return bool(self.cryptobot_token) and any(t.price_usdt for t in self.tariffs.values())

    @property
    def yookassa_enabled(self) -> bool:
        return (
            bool(self.yookassa_shop_id)
            and bool(self.yookassa_secret)
            and any(t.price_rub for t in self.tariffs.values())
        )


DEFAULT_TARIFFS = {
    "basic": {
        "title": "Подписка на 30 дней",
        "days": 30,
        "price_rub": 199,
        "price_stars": 150,
        "price_usdt": 1.99,
        "description": "Все локации • безлимитный трафик • до 3 устройств",
    }
}


def _parse_tariffs(raw: str) -> dict[str, Tariff]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConfigError(f"TARIFFS — невалидный JSON: {e}") from e
    if not isinstance(data, dict) or not data:
        raise ConfigError("TARIFFS должен быть непустым JSON-объектом {id: {...}}")

    tariffs: dict[str, Tariff] = {}
    for tid, item in data.items():
        if not isinstance(item, dict):
            raise ConfigError(f"Тариф «{tid}»: ожидается объект")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", tid):
            raise ConfigError(f"Тариф «{tid}»: id может содержать только a-z, 0-9, _ и -")
        days = int(item.get("days", 0))
        if days <= 0 or days > 3650:
            raise ConfigError(f"Тариф «{tid}»: days должен быть от 1 до 3650")
        stars = item.get("price_stars")
        if stars is not None and int(stars) < 1:
            raise ConfigError(f"Тариф «{tid}»: price_stars должен быть ≥ 1")
        tariffs[tid] = Tariff(
            id=tid,
            title=str(item.get("title") or f"Подписка на {days} дн."),
            days=days,
            description=str(item.get("description") or ""),
            price_rub=None if item.get("price_rub") is None else float(item["price_rub"]),
            price_stars=None if stars is None else int(stars),
            price_usdt=None if item.get("price_usdt") is None else float(item["price_usdt"]),
        )
    return tariffs


def load_config() -> Config:
    bot_token = _get("BOT_TOKEN")
    if not bot_token:
        raise ConfigError("BOT_TOKEN не задан. Заполните .env (см. .env.example).")
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", bot_token):
        raise ConfigError("BOT_TOKEN выглядит некорректно. Скопируйте токен из @BotFather целиком.")

    admin_ids = tuple(
        int(x) for x in _get("ADMIN_IDS").replace(" ", "").split(",") if x.isdigit()
    )

    panel_url = _get("REMNAWAVE_PANEL_URL").rstrip("/")
    if not panel_url:
        raise ConfigError("REMNAWAVE_PANEL_URL не задан. Пример: https://panel.example.com")
    if not panel_url.startswith(("http://", "https://")):
        raise ConfigError("REMNAWAVE_PANEL_URL должен начинаться с http:// или https://")

    api_token = _get("REMNAWAVE_API_TOKEN")
    if not api_token:
        raise ConfigError(
            "REMNAWAVE_API_TOKEN не задан. Создайте токен: панель → Настройки → API Tokens."
        )

    sub_page = _get("SUB_PAGE_DOMAIN") or None
    if sub_page and not sub_page.startswith(("http://", "https://")):
        raise ConfigError("SUB_PAGE_DOMAIN должен начинаться с http:// или https://")

    tz_name = _get("TZ", "Europe/Moscow")
    try:
        tz = ZoneInfo(tz_name)
    except Exception as e:
        raise ConfigError(f"TZ «{tz_name}» не распознан ({e}). Пример: Europe/Moscow") from e

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        panel_url=panel_url,
        api_token=api_token,
        api_prefix=_get("REMNAWAVE_API_PREFIX", "/api") or "/api",
        sub_page_domain=sub_page,
        squad_uuid=_get("REMNAWAVE_SQUAD_UUID") or None,
        reset_traffic_on_renew=_get_bool("RESET_TRAFFIC_ON_RENEW", True),
        cryptobot_token=_get("CRYPTOBOT_TOKEN") or None,
        cryptobot_testnet=_get_bool("CRYPTOBOT_TESTNET", False),
        yookassa_shop_id=_get("YOOKASSA_SHOP_ID") or None,
        yookassa_secret=_get("YOOKASSA_SECRET") or None,
        db_path=_get("DB_PATH", "data/bot.db"),
        tz=tz,
        support_url=_get("SUPPORT_URL") or None,
        tariffs=_parse_tariffs(_get("TARIFFS") or json.dumps(DEFAULT_TARIFFS)),
    )
