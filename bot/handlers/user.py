"""Пользовательские хэндлеры: старт, меню, моя подписка, помощь, QR."""
from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..keyboards import faq_menu, main_menu, no_sub_menu, sub_menu
from ..qr import qr_file
from ..remnawave import RemnaError
from ..services import (
    Runtime,
    subscription_card,
    subscription_kb,
    sys_new_user,
    trial_config,
)

router = Router(name="user")
log = logging.getLogger(__name__)

REF_RE = re.compile(r"ref_([a-z0-9_-]{2,32})")   # рекламная кампания
USER_REF_RE = re.compile(r"u(\d{3,})")           # персональная реферальная ссылка


async def _ensure_user(rt: Runtime, message_or_cb) -> None:
    from_user = message_or_cb.from_user
    if from_user:
        await rt.db.upsert_bot_user(
            from_user.id, from_user.username, from_user.first_name
        )


async def _menu(rt: Runtime, show_trial: bool | None = None):
    if show_trial is None:
        tcfg = await trial_config(rt)
        show_trial = bool(tcfg["enabled"] and tcfg["channel"])
    return main_menu(show_trial=show_trial)


@router.message(CommandStart())
async def cmd_start(message: Message, rt: Runtime, bot: Bot):
    source = None
    referred_by = None
    args = (message.text or "").split(maxsplit=1)
    if len(args) > 1:
        payload = args[1].strip()
        m = REF_RE.match(payload)
        if m:
            source = m.group(1)
        else:
            m = USER_REF_RE.match(payload)
            if m:
                referred_by = m.group(1)
    created = await rt.db.upsert_bot_user(
        message.from_user.id, message.from_user.username,
        message.from_user.first_name, source=source, referred_by=referred_by,
    )
    if created:
        await sys_new_user(
            rt, bot, message.from_user.id,
            message.from_user.first_name or "—", source, referred_by,
        )
    if created and rt.cfg.admin_ids:
        for admin_id in rt.cfg.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    texts.NOTIF_NEW_USER.format(
                        name=message.from_user.first_name or "—", uid=message.from_user.id,
                        source=source or ("реферал " + referred_by if referred_by else "—"),
                    ),
                )
            except Exception:
                pass
    await message.answer(
        texts.START.format(name=message.from_user.first_name or "друг"),
        reply_markup=await _menu(rt),
        disable_web_page_preview=True,
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, rt: Runtime):
    await _ensure_user(rt, message)
    await message.answer("Главное меню:", reply_markup=await _menu(rt))


@router.message(Command("help"))
async def cmd_help(message: Message, rt: Runtime):
    await _ensure_user(rt, message)
    await message.answer(
        texts.HELP, reply_markup=await _menu(rt), disable_web_page_preview=True
    )


@router.callback_query(F.data == "menu:main")
async def cb_main(query: CallbackQuery, state: FSMContext, rt: Runtime):
    await state.clear()
    await _ensure_user(rt, query)
    await query.message.edit_text(
        texts.START.format(name=query.from_user.first_name or "друг"),
        reply_markup=await _menu(rt),
        disable_web_page_preview=True,
    )
    await query.answer()


@router.callback_query(F.data == "menu:help")
async def cb_help(query: CallbackQuery, rt: Runtime):
    await query.message.edit_text(
        texts.HELP, reply_markup=main_menu(), disable_web_page_preview=True
    )
    await query.answer()


async def _rw_user_or_none(rt: Runtime, tg_id: int):
    try:
        return await rt.remna.get_user_by_telegram_id(tg_id)
    except RemnaError as e:
        log.error("get_user_by_telegram_id: %s", e)
        return None


@router.callback_query(F.data == "menu:sub")
async def cb_my_sub(query: CallbackQuery, rt: Runtime):
    await _ensure_user(rt, query)
    rw_user = await _rw_user_or_none(rt, query.from_user.id)
    if rw_user is None:
        await query.message.edit_text(texts.NO_SUBSCRIPTION, reply_markup=no_sub_menu())
        await query.answer()
        return
    text = subscription_card(rt, rw_user)
    try:
        url = rt.remna.build_sub_url(rw_user)
    except RemnaError:
        url = None
    if url:
        text += (
            f"\n\n🔗 <b>Ссылка для приложений</b> (нажмите, чтобы скопировать):\n"
            f"<code>{url}</code>"
        )
    expired = False
    from ..utils import parse_iso, utcnow

    expire = parse_iso(rw_user.get("expireAt"))
    disabled = str(rw_user.get("status", "")).upper() == "DISABLED"
    expired = disabled or (expire is not None and expire <= utcnow())
    kb = (
        no_sub_menu()
        if expired
        else sub_menu(url, buy_callback="buy") if url else no_sub_menu()
    )
    await query.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    await query.answer()


@router.callback_query(F.data == "menu:qr")
async def cb_qr(query: CallbackQuery, rt: Runtime):
    await query.answer()
    rw_user = await _rw_user_or_none(rt, query.from_user.id)
    if rw_user is None:
        await query.message.answer(texts.NO_SUBSCRIPTION, reply_markup=no_sub_menu())
        return
    try:
        url = rt.remna.build_sub_url(rw_user)
    except RemnaError as e:
        await query.message.answer(f"⚠️ {e}")
        return
    await query.message.answer_photo(
        qr_file(url),
        caption=texts.QR_CAPTION,
        reply_markup=subscription_kb(url),
    )


@router.callback_query(F.data == "menu:faq")
async def cb_faq(query: CallbackQuery, rt: Runtime):
    await query.message.edit_text(
        texts.FAQ_INTRO, reply_markup=faq_menu(texts.FAQ_ITEMS)
    )
    await query.answer()


@router.callback_query(F.data.startswith("faq:"))
async def cb_faq_item(query: CallbackQuery, rt: Runtime):
    idx = query.data.split(":", 1)[1]
    if not idx.isdigit() or int(idx) >= len(texts.FAQ_ITEMS):
        await query.answer()
        return
    q, a = texts.FAQ_ITEMS[int(idx)]
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ К вопросам", callback_data="menu:faq")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
    ])
    await query.message.edit_text(f"❓ <b>{q}</b>\n\n{a}", reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "my:payments")
async def cb_my_payments(query: CallbackQuery, rt: Runtime):
    from ..keyboards import my_payments_back_menu
    from ..utils import fmt_date, parse_iso

    payments = await rt.db.payments_for_user(query.from_user.id, limit=10)
    if not payments:
        await query.message.edit_text(
            texts.MY_PAYMENTS_EMPTY, reply_markup=my_payments_back_menu()
        )
        await query.answer()
        return
    icons = {"delivered": "✅", "paid": "✅", "pending": "⏳",
             "canceled": "❌", "error": "⚠️"}
    status_ru = {"delivered": "выдана", "paid": "оплачена", "pending": "ожидает",
                 "canceled": "отменена", "error": "ошибка"}
    cur_sym = {"RUB": "₽", "XTR": "⭐", "USDT": "USDT", "-": "", "days": "дн."}
    lines = ""
    real_payments = [p for p in payments if p["provider"] != "refbonus"]
    for p in real_payments:
        created = parse_iso(p["created_at"])
        tariff = rt.cfg.tariffs.get(p["tariff_id"])
        title = tariff.title if tariff else p["tariff_id"]
        amount = f"{p['amount']}{cur_sym.get(p['currency'], '')}".strip() or "—"
        lines += texts.MY_PAYMENTS_LINE.format(
            icon=icons.get(p["status"], "•"), id=p["id"],
            date=fmt_date(created, rt.cfg.tz), amount=amount,
            tariff=title, status=status_ru.get(p["status"], p["status"]),
        )
    total_all = await rt.db.payments_for_user(query.from_user.id, limit=1000)
    extra = len([p for p in total_all if p["provider"] != "refbonus"]) - len(real_payments)
    if extra > 0:
        lines += texts.MY_PAYMENTS_MORE.format(extra=extra)
    await query.message.edit_text(
        texts.MY_PAYMENTS_TITLE.format(list=lines), reply_markup=my_payments_back_menu()
    )
    await query.answer()
