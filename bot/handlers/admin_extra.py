"""Админка: промокоды, рекламные кампании, пробный период, способы оплаты."""
from __future__ import annotations

import re
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..keyboards import (
    admin_menu,
    campaign_list_menu,
    pay_toggles_menu,
    promo_detail_menu,
    promo_list_menu,
    trial_settings_menu,
)
from ..services import Runtime, trial_config
from ..utils import fmt_date, parse_iso, utcnow

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
    lines = "".join(
        texts.ADMIN_CAMP_LINE.format(
            name=c["name"],
            users=stats.get(c["name"], {}).get("users", 0),
            paid=stats.get(c["name"], {}).get("paid", 0),
            revenue=_revenue_str(stats.get(c["name"], {}).get("revenue", {})),
        )
        for c in campaigns
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
        "stars": rt.cfg.stars_enabled,
        "cryptobot": rt.cryptobot is not None and rt.cfg.cryptobot_enabled,
        "yookassa": rt.yookassa is not None and rt.cfg.yookassa_enabled,
    }
    states = {
        name: await rt.db.get_setting(f"pay_{name}", "1") == "1"
        for name in configured
    }
    labels = {"stars": "Telegram Stars", "cryptobot": "CryptoBot (USDT)", "yookassa": "ЮKassa (карты)"}
    lines = "".join(
        texts.ADMIN_PAY_LINE.format(
            icon="✅" if states[name] else "❌", label=labels[name],
        )
        for name, conf in configured.items() if conf
    ) or "ни один способ не сконфигурирован в .env"
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
