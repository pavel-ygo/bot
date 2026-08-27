"""Инлайн-клавиатуры бота."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu(*, support_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔑 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="💳 Моя подписка", callback_data="menu:sub")],
        [InlineKeyboardButton(text="📖 Как подключиться", callback_data="menu:help")],
    ]
    if support_url:
        rows.append([InlineKeyboardButton(text="🆘 Поддержка", url=support_url)])
    return _kb(rows)


def back_to_menu() -> list[list[InlineKeyboardButton]]:
    return [[InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]]


def tariffs_menu(tariffs: list) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{t.title} — {t.price_line()}", callback_data=f"tar:{t.id}")]
        for t in tariffs
    ]
    rows += back_to_menu()
    return _kb(rows)


def pay_methods_menu(tariff, providers: dict[str, bool]) -> InlineKeyboardMarkup:
    labels = {
        "stars": "⭐ Telegram Stars",
        "cryptobot": "🪙 Криптовалюта (USDT)",
        "yookassa": "💳 Карта (ЮKassa)",
    }
    rows = []
    for name, available in providers.items():
        if available:
            rows.append([
                InlineKeyboardButton(
                    text=labels.get(name, name), callback_data=f"pay:{tariff.id}:{name}"
                )
            ])
    rows += back_to_menu()
    return _kb(rows)


def pay_link_menu(url: str, payment_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=url)],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"chk:{payment_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cxl:{payment_id}")],
    ])


def sub_menu(url: str, *, buy_callback: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔗 Подключить", url=url)],
        [InlineKeyboardButton(text="📱 QR-код", callback_data="menu:qr")],
    ]
    if buy_callback:
        rows.append([InlineKeyboardButton(text="🔑 Продлить / купить", callback_data=buy_callback)])
    rows += back_to_menu()
    return _kb(rows)


def no_sub_menu() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="🔑 Купить подписку", callback_data="buy")],
        *back_to_menu(),
    ])


def admin_menu() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
        [
            InlineKeyboardButton(text="📡 Ноды", callback_data="adm:nodes"),
            InlineKeyboardButton(text="🔧 Проверка панели", callback_data="adm:check"),
        ],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:bcast")],
        [InlineKeyboardButton(text="🎁 Выдать подписку", callback_data="adm:grant")],
        [
            InlineKeyboardButton(text="🚫 Отключить юзера", callback_data="adm:ban"),
            InlineKeyboardButton(text="✅ Включить юзера", callback_data="adm:unban"),
        ],
    ])


def admin_confirm_broadcast() -> InlineKeyboardMarkup:
    return _kb([
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="adm:bcast:go"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel"),
        ]
    ])


def admin_back() -> InlineKeyboardMarkup:
    return _kb([[InlineKeyboardButton(text="⬅️ В админку", callback_data="adm:main")]])
