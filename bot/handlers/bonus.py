"""Пользовательские бонусы: активация промокодов и пробный период."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .. import texts
from ..config import Tariff
from ..keyboards import back_to_menu, main_menu
from ..services import (
    Runtime,
    deliver_subscription,
    is_channel_member,
    subscription_kb,
    sys_log,
    trial_config,
)

router = Router(name="bonus")
log = logging.getLogger(__name__)


class PromoStates(StatesGroup):
    waiting_code = State()


def _menu(rt: Runtime, show_trial: bool = False):
    return main_menu(support_url=rt.cfg.support_url, show_trial=show_trial)


# ──────────────────────────── промокоды ────────────────────────────


@router.callback_query(F.data == "promo")
async def cb_promo(query: CallbackQuery, state: FSMContext, rt: Runtime):
    await state.set_state(PromoStates.waiting_code)
    await query.message.edit_text(
        texts.PROMO_ASK,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=back_to_menu()),
    )
    await query.answer()


@router.message(PromoStates.waiting_code)
async def promo_input(message: Message, state: FSMContext, rt: Runtime, bot: Bot):
    code = (message.text or "").strip().upper()
    await state.clear()
    if not code or code.startswith("/"):
        await message.answer("Отменено.", reply_markup=_menu(rt))
        return

    promo, reason = await rt.db.activate_promo(code, message.from_user.id)
    if promo is None:
        answers = {
            "not_found": texts.PROMO_NOT_FOUND,
            "expired": texts.PROMO_EXPIRED,
            "limit": texts.PROMO_LIMIT,
            "already": texts.PROMO_ALREADY,
        }
        await message.answer(
            answers.get(reason, texts.PROMO_NOT_FOUND), reply_markup=_menu(rt)
        )
        return

    tariff = Tariff(
        id=f"promo_{promo['code'][:20]}",
        title=f"Промокод {promo['code']}",
        days=promo["days"],
        description="",
    )
    try:
        result_text, url = await deliver_subscription(rt, message.from_user.id, tariff)
    except Exception as e:
        log.exception("promo delivery failed: %s", e)
        await message.answer(texts.ERROR_DELIVERY)
        for admin_id in rt.cfg.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    f"⚠️ Ошибка выдачи по промокоду <code>{promo['code']}</code> "
                    f"для <a href=\"tg://user?id={message.from_user.id}\">юзера</a>:\n{e}",
                )
            except Exception:
                pass
        return

    await rt.db.add_payment(
        message.from_user.id, f"promo:{promo['code']}", "promo",
        "0", "-", status="delivered", note=f"promo={promo['code']}",
    )
    await message.answer(
        texts.PROMO_OK.format(code=promo["code"], days=promo["days"], result=result_text),
        reply_markup=subscription_kb(url),
        disable_web_page_preview=True,
    )
    await sys_log(rt, bot, texts.SYS_PROMO.format(
        code=promo["code"], days=promo["days"],
        uid=message.from_user.id,
        name=message.from_user.first_name or message.from_user.username or str(message.from_user.id),
    ))


# ──────────────────────────── пробный период ────────────────────────────


async def _grant_trial(rt: Runtime, bot: Bot, query: CallbackQuery, tcfg: dict) -> None:
    tariff = Tariff(id="trial", title="Пробный период", days=tcfg["days"], description="")
    traffic_limit = tcfg["traffic_gb"] * (1024 ** 3) if tcfg.get("traffic_gb") else None
    try:
        result_text, url = await deliver_subscription(
            rt, query.from_user.id, tariff, traffic_limit_bytes=traffic_limit
        )
    except Exception as e:
        log.exception("trial delivery failed: %s", e)
        await query.message.answer(texts.ERROR_DELIVERY)
        return
    await rt.db.mark_trial_used(query.from_user.id)
    await rt.db.add_payment(
        query.from_user.id, "trial", "trial", "0", "-",
        status="delivered", note=f"trial {tcfg['days']}d / {tcfg['traffic_gb']}gb",
    )
    done_text = (
        texts.TRIAL_OK_LIMITED.format(
            days=tcfg["days"], traffic_gb=tcfg["traffic_gb"], result=result_text,
        )
        if traffic_limit
        else texts.TRIAL_OK.format(days=tcfg["days"], result=result_text)
    )
    await query.message.edit_text(
        done_text,
        reply_markup=subscription_kb(url),
        disable_web_page_preview=True,
    )
    await sys_log(rt, bot, texts.SYS_TRIAL.format(
        uid=query.from_user.id,
        name=query.from_user.first_name or query.from_user.username or str(query.from_user.id),
        days=tcfg["days"],
    ))


async def _trial_check(rt: Runtime, bot: Bot, query: CallbackQuery, tcfg: dict) -> None:
    tg_id = query.from_user.id
    if await rt.db.trial_used(tg_id):
        await query.answer(texts.TRIAL_ALREADY, show_alert=True)
        return
    status = await is_channel_member(bot, tcfg["channel"], tg_id)
    if status is None:
        await query.answer(texts.TRIAL_UNAVAILABLE, show_alert=True)
        return
    if not status:
        await query.answer(texts.TRIAL_NOT_SUBSCRIBED, show_alert=True)
        return
    await query.answer()
    await _grant_trial(rt, bot, query, tcfg)


@router.callback_query(F.data == "trial")
async def cb_trial(query: CallbackQuery, rt: Runtime, bot: Bot):
    tcfg = await trial_config(rt)
    if not tcfg["enabled"]:
        await query.answer(texts.TRIAL_DISABLED, show_alert=True)
        return
    if await rt.db.trial_used(query.from_user.id):
        await query.answer(texts.TRIAL_ALREADY, show_alert=True)
        return

    # Канал не задан — выдаём без проверки подписки (сначала экран-подтверждение)
    if not tcfg["channel"]:
        rows = [[InlineKeyboardButton(
            text="🎉 Получить бесплатно", callback_data="trial:free",
        )]]
        rows += back_to_menu()
        await query.message.edit_text(
            texts.TRIAL_ASK_FREE.format(days=tcfg["days"], traffic_gb=tcfg["traffic_gb"]),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await query.answer()
        return

    rows: list[list[InlineKeyboardButton]] = []
    if tcfg["url"]:
        rows.append([InlineKeyboardButton(text="📢 Подписаться на канал", url=tcfg["url"])])
    rows.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="trial:check")])
    rows += back_to_menu()

    member = await is_channel_member(bot, tcfg["channel"], query.from_user.id)  # noqa: F841
    if member:
        await query.answer()
        await _grant_trial(rt, bot, query, tcfg)
        return
    await query.message.edit_text(
        texts.TRIAL_ASK.format(days=tcfg["days"]),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await query.answer()


@router.callback_query(F.data == "trial:free")
async def cb_trial_free(query: CallbackQuery, rt: Runtime, bot: Bot):
    tcfg = await trial_config(rt)
    if not tcfg["enabled"]:
        await query.answer(texts.TRIAL_DISABLED, show_alert=True)
        return
    if await rt.db.trial_used(query.from_user.id):
        await query.answer(texts.TRIAL_ALREADY, show_alert=True)
        return
    await query.answer()
    await _grant_trial(rt, bot, query, tcfg)


@router.callback_query(F.data == "trial:check")
async def cb_trial_check(query: CallbackQuery, rt: Runtime, bot: Bot):
    tcfg = await trial_config(rt)
    if not tcfg["enabled"] or not tcfg["channel"]:
        await query.answer(texts.TRIAL_DISABLED, show_alert=True)
        return
    await _trial_check(rt, bot, query, tcfg)


# ══════════════════════════ партнёрская программа ══════════════════════════


@router.callback_query(F.data == "ref")
async def cb_referral(query: CallbackQuery, rt: Runtime):
    tg_id = query.from_user.id
    bonus = rt.cfg.ref_bonus_days
    link = f"https://t.me/{rt.bot_username}?start=u{tg_id}"
    invited = await rt.db.count_referrals(tg_id)
    paid = await rt.db.paid_referrals(tg_id)
    earned = await rt.db.ref_bonus_days_total(tg_id)
    share_url = (
        f"https://t.me/share/url?url={link}&text="
        "Попробуй VPN по моей ссылке — недорого и работает!"
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=share_url)],
        *back_to_menu(),
    ])
    await query.message.edit_text(
        texts.REF_INFO.format(
            bonus=bonus, link=link, invited=invited, paid=paid, earned=earned,
        ),
        reply_markup=kb,
        disable_web_page_preview=True,
    )
    await query.answer()
