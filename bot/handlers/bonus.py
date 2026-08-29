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


# ──────────────────────────── пробный период ────────────────────────────


async def _grant_trial(rt: Runtime, bot: Bot, query: CallbackQuery, tcfg: dict) -> None:
    tariff = Tariff(id="trial", title="Пробный период", days=tcfg["days"], description="")
    try:
        result_text, url = await deliver_subscription(rt, query.from_user.id, tariff)
    except Exception as e:
        log.exception("trial delivery failed: %s", e)
        await query.message.answer(texts.ERROR_DELIVERY)
        return
    await rt.db.mark_trial_used(query.from_user.id)
    await rt.db.add_payment(
        query.from_user.id, "trial", "trial", "0", "-",
        status="delivered", note=f"trial {tcfg['days']}d",
    )
    await query.message.edit_text(
        texts.TRIAL_OK.format(days=tcfg["days"], result=result_text),
        reply_markup=subscription_kb(url),
        disable_web_page_preview=True,
    )


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
    if not tcfg["enabled"] or not tcfg["channel"]:
        await query.answer(texts.TRIAL_DISABLED, show_alert=True)
        return
    if await rt.db.trial_used(query.from_user.id):
        await query.answer(texts.TRIAL_ALREADY, show_alert=True)
        return

    rows: list[list[InlineKeyboardButton]] = []
    if tcfg["url"]:
        rows.append([InlineKeyboardButton(text="📢 Подписаться на канал", url=tcfg["url"])])
    rows.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="trial:check")])
    rows += back_to_menu()

    member = await is_channel_member(bot, tcfg["channel"], query.from_user.id)
    if member:
        await query.answer()
        await _grant_trial(rt, bot, query, tcfg)
        return
    await query.message.edit_text(
        texts.TRIAL_ASK.format(days=tcfg["days"]),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await query.answer()


@router.callback_query(F.data == "trial:check")
async def cb_trial_check(query: CallbackQuery, rt: Runtime, bot: Bot):
    tcfg = await trial_config(rt)
    if not tcfg["enabled"] or not tcfg["channel"]:
        await query.answer(texts.TRIAL_DISABLED, show_alert=True)
        return
    await _trial_check(rt, bot, query, tcfg)
