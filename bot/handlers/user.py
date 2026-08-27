"""Пользовательские хэндлеры: старт, меню, моя подписка, помощь, QR."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..keyboards import main_menu, no_sub_menu, sub_menu
from ..qr import qr_file
from ..remnawave import RemnaError
from ..services import Runtime, subscription_card, subscription_kb

router = Router(name="user")
log = logging.getLogger(__name__)


async def _ensure_user(rt: Runtime, message_or_cb) -> None:
    from_user = message_or_cb.from_user
    if from_user:
        await rt.db.upsert_bot_user(from_user.id, from_user.username, from_user.first_name)


def _menu(rt: Runtime):
    return main_menu(support_url=rt.cfg.support_url)


@router.message(CommandStart())
async def cmd_start(message: Message, rt: Runtime):
    await _ensure_user(rt, message)
    await message.answer(
        texts.START.format(name=message.from_user.first_name or "друг"),
        reply_markup=_menu(rt),
        disable_web_page_preview=True,
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, rt: Runtime):
    await _ensure_user(rt, message)
    await message.answer("Главное меню:", reply_markup=_menu(rt))


@router.message(Command("help"))
async def cmd_help(message: Message, rt: Runtime):
    await _ensure_user(rt, message)
    await message.answer(texts.HELP, reply_markup=_menu(rt), disable_web_page_preview=True)


@router.callback_query(F.data == "menu:main")
async def cb_main(query: CallbackQuery, rt: Runtime):
    await _ensure_user(rt, query)
    await query.message.edit_text(
        texts.START.format(name=query.from_user.first_name or "друг"),
        reply_markup=_menu(rt),
        disable_web_page_preview=True,
    )
    await query.answer()


@router.callback_query(F.data == "menu:help")
async def cb_help(query: CallbackQuery, rt: Runtime):
    await query.message.edit_text(
        texts.HELP, reply_markup=main_menu(support_url=None), disable_web_page_preview=True
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
