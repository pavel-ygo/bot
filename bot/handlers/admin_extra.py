"""Админка: промокоды, рекламные кампании, пробный период, способы оплаты."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import texts
from ..config import Tariff
from ..keyboards import (
    csv_menu,
    user_card_menu,
    admin_menu,
    campaign_list_menu,
    pay_toggles_menu,
    promo_detail_menu,
    promo_list_menu,
    trial_settings_menu,
)
from ..remnawave import RemnaError
from ..services import Runtime, deliver_subscription, subscription_kb, trial_config
from ..utils import fmt_date, parse_iso, utcnow


async def _resolve_target(rt: Runtime, target: str) -> dict | None:
    """TG ID или логин Remnawave -> пользователь панели."""
    target = target.strip().lstrip("@")
    if target.isdigit():
        user = await rt.remna.get_user_by_telegram_id(int(target))
        if user:
            return user
    return await rt.remna.get_user_by_username(target)

router = Router(name="admin-extra")


def _is_admin(rt: Runtime, user_id: int) -> bool:
    return user_id in rt.cfg.admin_ids


def _revenue_str(revenue: dict) -> str:
    if not revenue:
        return "—"
    symbols = {"RUB": "₽", "XTR": "⭐", "USDT": " USDT"}
    return " / ".join(f"{total:g}{symbols.get(cur, f' {cur}')}" for cur, total in revenue.items())


# ══════════════════════════ ПРОМОКОДЫ ══════════════════════════


class PromoFSM(StatesGroup):
    code = State()
    days = State()
    limit = State()
    expires = State()


async def _promo_list_text(rt: Runtime) -> str:
    promos = await rt.db.list_promos()
    if not promos:
        return texts.ADMIN_PROMO.format(list=texts.ADMIN_PROMO_EMPTY)
    lines = "".join(
        texts.ADMIN_PROMO_LINE.format(
            code=p["code"], days=p["days"], used=p["used"],
            max=p["max_uses"] or "∞",
            status=texts.ADMIN_PROMO_ON if p["active"] else texts.ADMIN_PROMO_OFF,
        )
        for p in promos
    )
    return texts.ADMIN_PROMO.format(list=lines)


@router.callback_query(F.data == "adm:promo")
async def cb_promo_list(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await query.message.edit_text(
        await _promo_list_text(rt), reply_markup=promo_list_menu(await rt.db.list_promos())
    )
    await query.answer()


@router.callback_query(F.data.startswith("adm:promo:info:"))
async def cb_promo_info(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    promo = await rt.db.get_promo(int(query.data.rsplit(":", 1)[1]))
    if promo is None:
        await query.answer(texts.PROMO_NOT_FOUND, show_alert=True)
        return
    expires = "бессрочно"
    if promo["expires_at"]:
        parsed = parse_iso(promo["expires_at"])
        expires = fmt_date(parsed, rt.cfg.tz) if parsed else promo["expires_at"]
    await query.message.edit_text(
        texts.ADMIN_PROMO_DETAIL.format(
            code=promo["code"], days=promo["days"], used=promo["used"],
            max=promo["max_uses"] or "∞", expires=expires,
            status=texts.ADMIN_TRIAL_ON if promo["active"] else texts.ADMIN_TRIAL_OFF,
        ),
        reply_markup=promo_detail_menu(promo),
    )
    await query.answer()


@router.callback_query(F.data.startswith("adm:promo:tg:"))
async def cb_promo_toggle(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    promo = await rt.db.get_promo(int(query.data.rsplit(":", 1)[1]))
    if promo is None:
        await query.answer(texts.PROMO_NOT_FOUND, show_alert=True)
        return
    await rt.db.set_promo_active(promo["id"], not promo["active"])
    await cb_promo_info(query, rt)


@router.callback_query(F.data.startswith("adm:promo:del:"))
async def cb_promo_delete(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await rt.db.delete_promo(int(query.data.rsplit(":", 1)[1]))
    await query.answer(texts.ADMIN_PROMO_DELETED, show_alert=True)
    await cb_promo_list(query, rt)


@router.callback_query(F.data == "adm:promo:new")
async def cb_promo_new(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.set_state(PromoFSM.code)
    await query.message.edit_text(texts.ADMIN_PROMO_NEW_ASK_CODE)
    await query.answer()


@router.message(PromoFSM.code)
async def promo_code_input(message: Message, state: FSMContext, rt: Runtime):
    code = (message.text or "").strip().upper()
    if code == "/CANCEL":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=admin_menu())
    if not re.fullmatch(r"[A-Z0-9_-]{3,32}", code):
        await message.answer("Код должен быть из латиницы/цифр, 3–32 символа. Попробуйте ещё раз:")
        return
    await state.update_data(code=code)
    await state.set_state(PromoFSM.days)
    await message.answer(texts.ADMIN_PROMO_NEW_ASK_DAYS)


@router.message(PromoFSM.days)
async def promo_days_input(message: Message, state: FSMContext, rt: Runtime):
    if not (message.text or "").strip().isdigit():
        await message.answer(texts.ADMIN_ASK_NUMBER)
        return
    days = int(message.text.strip())
    if not (1 <= days <= 3650):
        await message.answer("Дней должно быть от 1 до 3650:")
        return
    await state.update_data(days=days)
    await state.set_state(PromoFSM.limit)
    await message.answer(texts.ADMIN_PROMO_NEW_ASK_LIMIT)


@router.message(PromoFSM.limit)
async def promo_limit_input(message: Message, state: FSMContext, rt: Runtime):
    if not (message.text or "").strip().isdigit():
        await message.answer(texts.ADMIN_ASK_NUMBER)
        return
    await state.update_data(limit=int(message.text.strip()))
    await state.set_state(PromoFSM.expires)
    await message.answer(texts.ADMIN_PROMO_NEW_ASK_EXPIRES)


@router.message(PromoFSM.expires)
async def promo_expires_input(message: Message, state: FSMContext, rt: Runtime, bot: Bot):
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(texts.ADMIN_ASK_NUMBER)
        return
    data = await state.get_data()
    await state.clear()
    expires_at = None
    expires_str = "бессрочно"
    if int(raw) > 0:
        expires_at = (utcnow() + timedelta(days=int(raw))).isoformat()
        expires_str = f"через {raw} дн."

    if not await rt.db.create_promo(data["code"], data["days"], data["limit"], expires_at):
        await message.answer(texts.ADMIN_PROMO_EXISTS, reply_markup=admin_menu())
        return
    await message.answer(
        texts.ADMIN_PROMO_CREATED.format(
            code=data["code"], days=data["days"], max=data["limit"] or "∞", expires=expires_str,
        ),
        reply_markup=admin_menu(),
    )


# ══════════════════════════ РЕКЛАМНЫЕ КАМПАНИИ ══════════════════════════


class CampFSM(StatesGroup):
    name = State()


async def _camp_list_text(rt: Runtime) -> str:
    campaigns = await rt.db.list_campaigns()
    stats = await rt.db.campaign_stats()
    if not campaigns:
        return texts.ADMIN_CAMP.format(list=texts.ADMIN_CAMP_EMPTY)
    lines = ""
    for c in campaigns:
        item = stats.get(c["name"], {})
        users = item.get("users", 0)
        paid = item.get("paid", 0)
        conv = f"{paid / users * 100:.0f}%" if users else "—"
        lines += texts.ADMIN_CAMP_LINE.format(
            name=c["name"], users=users, paid=paid, conv=conv,
            revenue=_revenue_str(item.get("revenue", {})),
        )
    return texts.ADMIN_CAMP.format(list=lines)


@router.callback_query(F.data == "adm:camp")
async def cb_camp_list(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await query.message.edit_text(
        await _camp_list_text(rt),
        reply_markup=campaign_list_menu(await rt.db.list_campaigns()),
    )
    await query.answer()


@router.callback_query(F.data.startswith("adm:camp:del:"))
async def cb_camp_delete(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await rt.db.delete_campaign(int(query.data.rsplit(":", 1)[1]))
    await query.answer(texts.ADMIN_CAMP_DELETED, show_alert=True)
    await cb_camp_list(query, rt)


@router.callback_query(F.data == "adm:camp:new")
async def cb_camp_new(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.set_state(CampFSM.name)
    await query.message.edit_text(texts.ADMIN_CAMP_NEW_ASK)
    await query.answer()


@router.message(CampFSM.name)
async def camp_name_input(message: Message, state: FSMContext, rt: Runtime):
    name = (message.text or "").strip().lower().lstrip("@")
    await state.clear()
    if name == "/cancel":
        return await message.answer("Отменено.", reply_markup=admin_menu())
    if not re.fullmatch(r"[a-z0-9_-]{2,32}", name):
        await message.answer(
            "Имя: латиница/цифры/дефис, 2–32 символа. Попробуйте ещё раз:",
            reply_markup=admin_menu(),
        )
        return
    if not await rt.db.add_campaign(name):
        await message.answer(texts.ADMIN_CAMP_EXISTS, reply_markup=admin_menu())
        return
    await message.answer(
        texts.ADMIN_CAMP_CREATED.format(name=name, link=f"https://t.me/{rt.bot_username}?start=ref_{name}"),
        reply_markup=admin_menu(),
        disable_web_page_preview=True,
    )


# ══════════════════════════ ПРОБНЫЙ ПЕРИОД ══════════════════════════


class TrialFSM(StatesGroup):
    channel = State()
    url = State()
    days = State()


async def _trial_text_and_kb(rt: Runtime):
    tcfg = await trial_config(rt)
    used = await rt.db.trials_count()
    text = texts.ADMIN_TRIAL.format(
        status=texts.ADMIN_TRIAL_ON if tcfg["enabled"] else texts.ADMIN_TRIAL_OFF,
        days=tcfg["days"],
        channel=tcfg["channel"] or "не задан",
        url=tcfg["url"] or "не задана",
        used=used,
    )
    return text, trial_settings_menu(tcfg["enabled"])


@router.callback_query(F.data == "adm:trial")
async def cb_trial_menu(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    text, kb = await _trial_text_and_kb(rt)
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "adm:trial:toggle")
async def cb_trial_toggle(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    tcfg = await trial_config(rt)
    await rt.db.set_setting("trial_enabled", "0" if tcfg["enabled"] else "1")
    text, kb = await _trial_text_and_kb(rt)
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer("Сохранено")


@router.callback_query(F.data == "adm:trial:chan")
async def cb_trial_chan(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.set_state(TrialFSM.channel)
    await query.message.edit_text(texts.ADMIN_TRIAL_SET_CHANNEL)
    await query.answer()


@router.message(TrialFSM.channel)
async def trial_chan_input(message: Message, state: FSMContext, rt: Runtime):
    channel = (message.text or "").strip()
    await state.clear()
    if channel.lower() == "/cancel":
        return await message.answer("Отменено.", reply_markup=admin_menu())
    if not (channel.startswith("@") or channel.lstrip("-").isdigit()):
        await message.answer("Нужен @username или числовой ID. Попробуйте ещё раз:")
        return
    await rt.db.set_setting("trial_channel", channel)
    await message.answer(
        texts.ADMIN_TRIAL_SET_OK.format(key="канал", value=channel),
        reply_markup=admin_menu(),
    )


@router.callback_query(F.data == "adm:trial:url")
async def cb_trial_url(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.set_state(TrialFSM.url)
    await query.message.edit_text(texts.ADMIN_TRIAL_SET_URL)
    await query.answer()


@router.message(TrialFSM.url)
async def trial_url_input(message: Message, state: FSMContext, rt: Runtime):
    url = (message.text or "").strip()
    await state.clear()
    if url.lower() == "/cancel":
        return await message.answer("Отменено.", reply_markup=admin_menu())
    if not url.startswith("https://t.me/"):
        await message.answer("Ссылка должна начинаться с https://t.me/. Попробуйте ещё раз:")
        return
    await rt.db.set_setting("trial_channel_url", url)
    await message.answer(
        texts.ADMIN_TRIAL_SET_OK.format(key="ссылка", value=url),
        reply_markup=admin_menu(),
    )


@router.callback_query(F.data == "adm:trial:days")
async def cb_trial_days(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.set_state(TrialFSM.days)
    await query.message.edit_text(texts.ADMIN_TRIAL_SET_DAYS)
    await query.answer()


@router.message(TrialFSM.days)
async def trial_days_input(message: Message, state: FSMContext, rt: Runtime):
    raw = (message.text or "").strip()
    await state.clear()
    if raw.lower() == "/cancel":
        return await message.answer("Отменено.", reply_markup=admin_menu())
    if not raw.isdigit() or not (1 <= int(raw) <= 365):
        await message.answer("Число от 1 до 365. Попробуйте ещё раз:")
        return
    await rt.db.set_setting("trial_days", raw)
    await message.answer(
        texts.ADMIN_TRIAL_SET_OK.format(key="срок", value=f"{raw} дн."),
        reply_markup=admin_menu(),
    )


# ══════════════════════════ СПОСОБЫ ОПЛАТЫ ══════════════════════════


async def _pay_text_and_kb(rt: Runtime):
    configured = {
        "card": bool(await rt.db.get_setting("card_number", "")),
        "yookassa": rt.yookassa is not None and rt.cfg.yookassa_enabled,
        "stars": rt.cfg.stars_enabled,
        "cryptobot": rt.cryptobot is not None and rt.cfg.cryptobot_enabled,
    }
    defaults = {"card": "1", "yookassa": "0", "stars": "0", "cryptobot": "0"}
    states = {
        name: await rt.db.get_setting(f"pay_{name}", defaults[name]) == "1"
        for name in configured
    }
    labels = {"card": "Перевод на карту (ручное подтверждение)", "yookassa": "ЮKassa (карты)",
              "stars": "Telegram Stars", "cryptobot": "CryptoBot (USDT)"}
    lines = "".join(
        texts.ADMIN_PAY_LINE.format(
            icon="✅" if states[name] else "❌", label=labels[name],
        )
        for name, conf in configured.items() if conf
    ) or "ни один способ не настроен"
    return texts.ADMIN_PAY.format(list=lines), pay_toggles_menu(states, configured)


@router.callback_query(F.data == "adm:pay")
async def cb_pay_menu(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    text, kb = await _pay_text_and_kb(rt)
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer()


@router.callback_query(F.data.startswith("adm:pay:"))
async def cb_pay_toggle(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    name = query.data.rsplit(":", 1)[1]
    if name not in ("stars", "cryptobot", "yookassa"):
        await query.answer()
        return
    current = await rt.db.get_setting(f"pay_{name}", "1") == "1"
    await rt.db.set_setting(f"pay_{name}", "0" if current else "1")
    text, kb = await _pay_text_and_kb(rt)
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer("Сохранено")


# ══════════════════════════ КАРТОЧКА ПОЛЬЗОВАТЕЛЯ ══════════════════════════


class UserCardFSM(StatesGroup):
    target = State()
    extend_days = State()


async def _render_user_card(rt: Runtime, rw_user: dict | None, target: str) -> tuple[str, Any]:
    """Собирает карточку. rw_user может быть None (нет в Remnawave)."""
    tg_id = None
    bot_user = None
    if target.isdigit():
        tg_id = int(target)
        bot_user = await rt.db.get_bot_user(tg_id)
    elif rw_user and rw_user.get("telegramId"):
        try:
            tg_id = int(rw_user["telegramId"])
        except (TypeError, ValueError):
            tg_id = None
        bot_user = await rt.db.get_bot_user(tg_id)

    payments = await rt.db.payments_for_user(tg_id, limit=5) if tg_id else []
    if payments:
        lines = ""
        cur_sym = {"RUB": "₽", "XTR": "⭐", "USDT": " USDT"}
        status_ru = {"delivered": "✅", "paid": "✅", "pending": "⏳",
                     "canceled": "❌", "error": "⚠️"}
        for pay in payments:
            created = parse_iso(pay["created_at"])
            lines += (
                f"├ #{pay['id']} {fmt_date(created, rt.cfg.tz)} — "
                f"{pay['amount']}{cur_sym.get(pay['currency'], '')} "
                f"({pay['provider']}) {status_ru.get(pay['status'], pay['status'])}\n"
            )
    else:
        lines = "├ " + texts.ADMIN_USER_NO_PAYMENTS + "\n"

    source = "— напрямую"
    if bot_user:
        if bot_user.get("source"):
            source = f"реклама «{bot_user['source']}»"
        elif bot_user.get("referred_by"):
            source = f"реферал <code>{bot_user['referred_by']}</code>"

    referrals = await rt.db.count_referrals(tg_id) if tg_id else 0
    paid_ref = await rt.db.paid_referrals(tg_id) if tg_id else 0

    if rw_user:
        from ..utils import fmt_bytes

        expire = parse_iso(rw_user.get("expireAt"))
        used = rw_user.get("usedTrafficBytes")
        if used is None:
            used = (rw_user.get("userTraffic") or {}).get("usedTrafficBytes")
        traffic = fmt_bytes(used)
        limit_b = rw_user.get("trafficLimitBytes")
        if limit_b:
            traffic += " / " + fmt_bytes(limit_b)
        rw_block = {
            "rw_username": rw_user.get("username", "—"),
            "rw_status": rw_user.get("status", "—"),
            "expire": fmt_date(expire, rt.cfg.tz),
            "traffic": traffic,
        }
    else:
        rw_block = {
            "rw_username": "— (нет в Remnawave)",
            "rw_status": "—",
            "expire": "—",
            "traffic": "—",
        }

    if tg_id:
        name = bot_user.get("first_name") if bot_user else None
        uname = bot_user.get("username") if bot_user else None
        tg_line = (
            f"<a href=\"tg://user?id={tg_id}\">{name or uname or tg_id}</a> (<code>{tg_id}</code>)"
        )
    else:
        tg_line = texts.ADMIN_USER_NOT_IN_BOT

    text = texts.ADMIN_USER_CARD.format(
        tg_line=tg_line,
        referrals=referrals,
        paid_ref=paid_ref,
        trial=("использован" if bot_user and bot_user.get("trial_used") else "нет"),
        payments=lines,
        source=source,
        **rw_block,
    )
    disabled = bool(rw_user and str(rw_user.get("status", "")).upper() == "DISABLED")
    kb = user_card_menu(tg_id, rw_user.get("uuid") if rw_user else None, disabled)
    return text, kb


@router.callback_query(F.data == "adm:user")
async def cb_user_card(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.set_state(UserCardFSM.target)
    await query.message.edit_text(texts.ADMIN_USER_ASK)
    await query.answer()


@router.message(UserCardFSM.target)
async def user_card_input(message: Message, state: FSMContext, rt: Runtime):
    target = (message.text or "").strip().lstrip("@")
    if target.lower() == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=admin_menu())
    if not target:
        return
    rw_user = await _resolve_target(rt, target)
    if rw_user is None and not target.isdigit():
        await message.answer(texts.ADMIN_USER_NOT_FOUND)
        return
    await state.clear()
    await state.update_data(uc_target=target)
    text, kb = await _render_user_card(rt, rw_user, target)
    await message.answer(text, reply_markup=kb, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("adm:uc:toggle:"))
async def cb_user_card_toggle(query: CallbackQuery, rt: Runtime, bot: Bot):
    if not _is_admin(rt, query.from_user.id):
        return
    uuid = query.data.rsplit(":", 1)[1]
    try:
        rw_user = await rt.remna.get_user(uuid)
    except RemnaError as e:
        await query.answer(f"Ошибка: {e}", show_alert=True)
        return
    disable = str(rw_user.get("status", "")).upper() != "DISABLED"
    try:
        if disable:
            await rt.remna.disable_user(uuid)
        else:
            await rt.remna.enable_user(uuid)
    except RemnaError as e:
        await query.answer(f"Ошибка: {e}", show_alert=True)
        return
    await query.answer("Готово")
    text, kb = await _render_user_card(rt, rw_user, str(rw_user.get("telegramId") or uuid))
    try:
        await query.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        pass


@router.callback_query(F.data == "adm:uc:extend")
async def cb_user_card_extend(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.set_state(UserCardFSM.extend_days)
    await query.message.answer(texts.ADMIN_USER_EXTEND_ASK)
    await query.answer()


@router.message(UserCardFSM.extend_days)
async def user_card_extend_days(message: Message, state: FSMContext, rt: Runtime, bot: Bot):
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(texts.ADMIN_ASK_NUMBER)
        return
    days = int(raw)
    data = await state.get_data()
    await state.clear()
    target = data.get("uc_target")
    if not target:
        await message.answer("Пользователь не выбран. Начните заново: /admin")
        return
    rw_user = await _resolve_target(rt, target)
    tariff = Tariff(id="gift", title=f"Продление админом ({days} дн.)", days=days, description="")
    try:
        result_text, url = await deliver_subscription(
            rt, int(target) if target.isdigit() else None, tariff, existing=rw_user
        )
    except RemnaError as e:
        await message.answer(f"❌ Ошибка: {e}")
        return
    await rt.db.add_payment(
        int(target) if target.isdigit() else 0, "gift", "admin", "0", "-",
        status="delivered", note=f"card extend {days}d target={target}",
    )
    await message.answer(texts.ADMIN_GRANT_DONE.format(details=result_text),
                         disable_web_page_preview=True)
    notify_tg = int(target) if target.isdigit() else None
    if notify_tg is None and rw_user and rw_user.get("telegramId"):
        try:
            notify_tg = int(rw_user["telegramId"])
        except (TypeError, ValueError):
            notify_tg = None
    if notify_tg:
        try:
            await bot.send_message(
                notify_tg, "🎁 Администратор продлил вам подписку!\n\n" + result_text,
                reply_markup=subscription_kb(url), disable_web_page_preview=True,
            )
        except Exception:
            pass


# ══════════════════════════ CSV-ЭКСПОРТ ══════════════════════════


@router.callback_query(F.data == "adm:csv")
async def cb_csv_menu(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await query.message.edit_text(texts.ADMIN_CSV_MENU, reply_markup=csv_menu())
    await query.answer()


def _csv_response(filename: str, header: list[str], rows: list[list]) -> BufferedInputFile:
    import csv as csvlib
    import io

    buf = io.StringIO()
    writer = csvlib.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return BufferedInputFile(buf.getvalue().encode("utf-8-sig"), filename=filename)


@router.callback_query(F.data == "adm:csv:payments")
async def cb_csv_payments(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await query.answer("Готовлю файл…")
    rows = [
        [p["id"], p["created_at"], p["tg_id"], p["tariff_id"], p["provider"],
         p["amount"], p["currency"], p["status"], p["source"] or ""]
        for p in await rt.db.all_payments()
    ]
    file = _csv_response(
        f"payments_{datetime.now():%Y%m%d}.csv",
        ["id", "created_at", "tg_id", "tariff", "provider", "amount", "currency",
         "status", "source"],
        rows,
    )
    await query.message.answer_document(file, caption=f"🧾 Платежи: {len(rows)}")


@router.callback_query(F.data == "adm:csv:users")
async def cb_csv_users(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await query.answer("Готовлю файл…")
    rows = [
        [u["tg_id"], u["username"] or "", u["created_at"], u["source"] or "",
         u["referred_by"] or "", "yes" if u["trial_used"] else "no"]
        for u in await rt.db.all_bot_users_full()
    ]
    file = _csv_response(
        f"users_{datetime.now():%Y%m%d}.csv",
        ["tg_id", "username", "created_at", "source", "referred_by", "trial_used"],
        rows,
    )
    await query.message.answer_document(file, caption=f"👥 Пользователи: {len(rows)}")
