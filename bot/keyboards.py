"""Инлайн-клавиатуры бота."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu(*, support_url: str | None = None, show_trial: bool = False) -> InlineKeyboardMarkup:
    bonus_row: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text="🎫 Промокод", callback_data="promo")
    ]
    if show_trial:
        bonus_row.append(InlineKeyboardButton(text="🎁 Пробный период", callback_data="trial"))
    rows = [
        [InlineKeyboardButton(text="🔑 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="💳 Моя подписка", callback_data="menu:sub")],
        bonus_row,
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
    rows.append([InlineKeyboardButton(text="🎫 У меня есть промокод", callback_data="promo")])
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
        [
            InlineKeyboardButton(text="🎫 Промокоды", callback_data="adm:promo"),
            InlineKeyboardButton(text="🔗 Рекламные ссылки", callback_data="adm:camp"),
        ],
        [
            InlineKeyboardButton(text="🎁 Пробный период", callback_data="adm:trial"),
            InlineKeyboardButton(text="💳 Способы оплаты", callback_data="adm:pay"),
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


# ── промокоды ──────────────────────────────────────────────────────────


def promo_list_menu(promos: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for p in promos:
        icon = "✅" if p["active"] else "⛔️"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {p['code']} — {p['days']} дн. ({p['used']}/{p['max_uses'] or '∞'})",
                callback_data=f"adm:promo:info:{p['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="➕ Создать промокод", callback_data="adm:promo:new")])
    rows += admin_back().inline_keyboard
    return _kb(rows)


def promo_detail_menu(promo: dict) -> InlineKeyboardMarkup:
    toggle_label = "⛔️ Выключить" if promo["active"] else "✅ Включить"
    return _kb([
        [InlineKeyboardButton(text=toggle_label, callback_data=f"adm:promo:tg:{promo['id']}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:promo:del:{promo['id']}")],
        [InlineKeyboardButton(text="⬅️ К списку", callback_data="adm:promo")],
    ])


# ── рекламные кампании ─────────────────────────────────────────────────


def campaign_list_menu(campaigns: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"🗑 {c['name']}", callback_data=f"adm:camp:del:{c['id']}",
        )]
        for c in campaigns
    ]
    rows.append([InlineKeyboardButton(text="➕ Создать ссылку", callback_data="adm:camp:new")])
    rows += admin_back().inline_keyboard
    return _kb(rows)


# ── пробный период ─────────────────────────────────────────────────────


def trial_settings_menu(enabled: bool) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(
            text="⛔️ Выключить" if enabled else "✅ Включить", callback_data="adm:trial:toggle",
        )],
        [
            InlineKeyboardButton(text="📣 Канал", callback_data="adm:trial:chan"),
            InlineKeyboardButton(text="🔗 Ссылка", callback_data="adm:trial:url"),
        ],
        [InlineKeyboardButton(text="📅 Срок (дни)", callback_data="adm:trial:days")],
        *admin_back().inline_keyboard,
    ])


# ── способы оплаты ─────────────────────────────────────────────────────


def pay_toggles_menu(states: dict[str, bool], available: dict[str, bool]) -> InlineKeyboardMarkup:
    labels = {"stars": "⭐ Telegram Stars", "cryptobot": "🪙 CryptoBot (USDT)",
              "yookassa": "💳 ЮKassa (карты)"}
    rows = []
    for name in ("stars", "cryptobot", "yookassa"):
        if not available.get(name):
            continue  # способ не сконфигурирован в .env — скрываем
        icon = "✅" if states.get(name) else "❌"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {labels[name]}", callback_data=f"adm:pay:{name}",
        )])
    rows += admin_back().inline_keyboard
    return _kb(rows)
