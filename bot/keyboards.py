"""Инлайн-клавиатуры бота."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu(*, show_trial: bool = False) -> InlineKeyboardMarkup:
    bonus_row: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text="🎫 Промокод", callback_data="promo")
    ]
    if show_trial:
        bonus_row.append(InlineKeyboardButton(text="🎁 Пробный период", callback_data="trial"))
    rows = [
        [InlineKeyboardButton(text="🔑 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="💳 Моя подписка", callback_data="menu:sub")],
        bonus_row,
        [InlineKeyboardButton(text="👥 Друзья", callback_data="ref"),
         InlineKeyboardButton(text="❓ FAQ", callback_data="menu:faq")],
        [InlineKeyboardButton(text="📖 Как подключиться", callback_data="menu:help")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
    ]
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
        "card": "🏦 Перевод на карту",
        "yookassa": "💳 Карта онлайн (ЮKassa)",
        "stars": "⭐ Telegram Stars",
        "cryptobot": "🪙 Криптовалюта (USDT)",
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
        [
            InlineKeyboardButton(text="🎫 Обращения", callback_data="adm:tickets"),
            InlineKeyboardButton(text="👤 Пользователь", callback_data="adm:user"),
        ],
        [InlineKeyboardButton(text="📤 Экспорт CSV", callback_data="adm:csv")],
        [InlineKeyboardButton(text="🏦 Оплата на карту", callback_data="adm:card")],
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
    labels = {"card": "🏦 Перевод на карту", "yookassa": "💳 ЮKassa (карты)",
              "stars": "⭐ Telegram Stars", "cryptobot": "🪙 CryptoBot (USDT)"}
    rows = []
    for name in ("card", "yookassa", "stars", "cryptobot"):
        if not available.get(name):
            continue  # способ не сконфигурирован — скрываем
        icon = "✅" if states.get(name) else "❌"
        cb = "adm:card" if name == "card" else f"adm:pay:{name}"
        rows.append([InlineKeyboardButton(text=f"{icon} {labels[name]}", callback_data=cb)])
    rows += admin_back().inline_keyboard
    return _kb(rows)


# ── FAQ ────────────────────────────────────────────────────────────────


def faq_menu(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=q, callback_data=f"faq:{i}")]
        for i, (q, _) in enumerate(items)
    ]
    rows.append([InlineKeyboardButton(text="🆘 Задать вопрос в поддержку", callback_data="support")])
    rows += back_to_menu()
    return _kb(rows)


# ── поддержка (тикеты) ─────────────────────────────────────────────────


def ticket_user_menu(ticket_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="✅ Вопрос решён — закрыть", callback_data=f"tk:close:{ticket_id}")],
    ])


def ticket_admin_menu(ticket_id: int, answered: bool) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"adm:tk:reply:{ticket_id}")],
        [InlineKeyboardButton(text="✅ Закрыть", callback_data=f"adm:tk:close:{ticket_id}")],
    ])


def tickets_list_menu(tickets: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{'🟡' if t['status'] == 'answered' else '🔴'} #{t['id']} — от {t['tg_id']}",
            callback_data=f"adm:tk:{t['id']}",
        )]
        for t in tickets
    ]
    rows += admin_back().inline_keyboard
    return _kb(rows)


# ── CSV ────────────────────────────────────────────────────────────────


def csv_menu() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="🧾 Платежи (все)", callback_data="adm:csv:payments")],
        [InlineKeyboardButton(text="👥 Пользователи (все)", callback_data="adm:csv:users")],
        *admin_back().inline_keyboard,
    ])


# ── карточка пользователя ──────────────────────────────────────────────


def user_card_menu(tg_id: int | None, rw_uuid: str | None, disabled: bool) -> InlineKeyboardMarkup:
    rows = []
    if tg_id:
        rows.append([InlineKeyboardButton(text="➕ Продлить", callback_data="adm:uc:extend")])
    if rw_uuid:
        rows.append([InlineKeyboardButton(
            text="✅ Включить" if disabled else "🚫 Отключить",
            callback_data=f"adm:uc:toggle:{rw_uuid}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ В админку", callback_data="adm:main")])
    return _kb(rows)


# ── оплата на карту ────────────────────────────────────────────────────


def card_pay_menu(payment_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"pc:sent:{payment_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cxl:{payment_id}")],
    ])


def card_receipt_admin_menu(payment_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"pc:ok:{payment_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"pc:no:{payment_id}"),
        ]
    ])


def card_receipt_auto_menu(payment_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="✅ Деньги пришли", callback_data=f"pc:verify:{payment_id}")],
        [InlineKeyboardButton(text="🚫 Не оплатил — отключить", callback_data=f"pc:revoke:{payment_id}")],
    ])


def admin_card_menu(enabled: bool, has_card: bool, auto: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text="⛔️ Выключить" if enabled else "✅ Включить", callback_data="adm:card:toggle",
        )],
        [InlineKeyboardButton(
            text="⚙️ Автоподтверждение чеков: вкл" if auto
            else "⚙️ Автоподтверждение чеков: выкл",
            callback_data="adm:card:auto",
        )],
        [InlineKeyboardButton(text="💳 Номер карты", callback_data="adm:card:set:num")],
        [
            InlineKeyboardButton(text="🏦 Банк", callback_data="adm:card:set:bank"),
            InlineKeyboardButton(text="👤 Получатель", callback_data="adm:card:set:holder"),
        ],
        [InlineKeyboardButton(text="📲 СБП (телефон)", callback_data="adm:card:set:sbp")],
    ]
    if has_card:
        rows.append([InlineKeyboardButton(text="🗑 Удалить реквизиты", callback_data="adm:card:del")])
    rows += admin_back().inline_keyboard
    return _kb(rows)


# ── отклонение чека с причиной ────────────────────────────────────────


def card_reject_reasons_menu(payment_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="💸 Неверная сумма", callback_data=f"pc:no2:{payment_id}:sum")],
        [InlineKeyboardButton(text="🖼 Чек не читается / не тот",
                              callback_data=f"pc:no2:{payment_id}:unreadable")],
        [InlineKeyboardButton(text="🔍 Платёж не найден", callback_data=f"pc:no2:{payment_id}:notfound")],
        [InlineKeyboardButton(text="✍️ Своя причина…", callback_data=f"pc:no2:{payment_id}:custom")],
    ])


# ── напоминание о брошенной оплате ────────────────────────────────────


def payment_nudge_menu(payment_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="💳 Показать реквизиты", callback_data=f"pc:show:{payment_id}")],
        [InlineKeyboardButton(text="❌ Не планирую платить", callback_data=f"cxl:{payment_id}")],
    ])


# ── сегменты рассылки ─────────────────────────────────────────────────


def broadcast_audience_menu() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(text="👥 Все пользователи", callback_data="adm:bc:aud:all")],
        [InlineKeyboardButton(text="⏳ Подписка истекает (≤3 дн.)", callback_data="adm:bc:aud:expiring")],
        [InlineKeyboardButton(text="🛑 Без активной подписки", callback_data="adm:bc:aud:no_sub")],
        [InlineKeyboardButton(text="❌ Ни одной оплаты", callback_data="adm:bc:aud:never_paid")],
        [InlineKeyboardButton(text="💳 Платили хотя бы раз", callback_data="adm:bc:aud:paid")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:cancel")],
    ])
