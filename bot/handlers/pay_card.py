"""Оплата переводом на карту: чек от пользователя → подтверждение админом → выдача."""
from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..keyboards import (admin_back, admin_card_menu, card_pay_menu,
                         card_receipt_admin_menu, card_receipt_auto_menu)
from ..services import Runtime, card_settings, complete_payment

router = Router(name="pay-card")
log = logging.getLogger(__name__)

RECEIPT_TYPES = {"photo", "document", "video", "text", "voice", "audio"}


class CardPayStates(StatesGroup):
    waiting_receipt = State()


class CardSettingsStates(StatesGroup):
    number = State()
    bank = State()
    holder = State()
    sbp = State()


def _is_admin(rt: Runtime, user_id: int) -> bool:
    return user_id in rt.cfg.admin_ids


async def _card_text(rt: Runtime, tariff, amount: float) -> str:
    cs = await card_settings(rt)
    bank_line = texts.CARD_BANK_LINE.format(bank=cs["bank"]) if cs["bank"] else ""
    holder_line = (
        texts.CARD_HOLDER_LINE.format(holder=cs["holder"]) if cs["holder"] else ""
    )
    sbp_line = texts.CARD_SBP_LINE.format(sbp=cs["sbp"]) if cs["sbp"] else ""
    return texts.CARD_PAY_TEXT.format(
        title=tariff.title, days=tariff.days, amount=f"{amount:g} ₽",
        card=cs["number"], bank_line=bank_line, holder_line=holder_line,
        sbp_line=sbp_line,
    )


# ══════════════════════════ пользователь ══════════════════════════


@router.callback_query(F.data == "pc:sent:")
async def cb_sent_empty(query: CallbackQuery):
    await query.answer()
    await query.message.answer(texts.CARD_RECEIPT_ASK)


@router.callback_query(F.data.startswith("pc:sent:"))
async def cb_i_paid(query: CallbackQuery, state: FSMContext, rt: Runtime):
    raw = query.data.rsplit(":", 1)[1]
    if not raw.isdigit():
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    payment = await rt.db.get_payment(int(raw))
    if not payment or payment["status"] != "pending":
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    await state.set_state(CardPayStates.waiting_receipt)
    await state.update_data(pid=int(raw))
    await query.message.answer(texts.CARD_RECEIPT_ASK)
    await query.answer()


@router.message(CardPayStates.waiting_receipt, F.content_type.in_(RECEIPT_TYPES))
async def card_receipt(message: Message, state: FSMContext, rt: Runtime, bot: Bot):
    await state.clear()
    if (message.text or "").strip().startswith("/cancel"):
        await message.answer("Отменено.")
        return
    await process_card_receipt(rt, bot, message)


async def process_card_receipt(rt: Runtime, bot: Bot, message: Message) -> bool:
    """Обрабатывает сообщение как чек к последней pending-оплате картой.

    Работает и после перезапуска бота (когда FSM-состояние потеряно).
    Возвращает True, если сообщение обработано как чек.
    """
    payment = await rt.db.latest_pending_card_payment(message.from_user.id)
    if payment is None:
        return False
    pid = payment["id"]

    tariff = rt.cfg.tariffs.get(payment["tariff_id"])
    bot_user = await rt.db.get_bot_user(message.from_user.id) or {}
    name = bot_user.get("first_name") or bot_user.get("username") or str(message.from_user.id)
    admin_info = texts.CARD_TO_ADMIN.format(
        pid=pid,
        title=tariff.title if tariff else payment["tariff_id"],
        days=tariff.days if tariff else "?",
        amount=f"{float(payment['amount']):g} ₽",
        uid=message.from_user.id, name=name,
    )

    auto = await rt.db.get_setting("auto_approve_receipts", "0") == "1"
    if auto:
        # ── доверительный режим: выдаём подписку сразу, админ проверяет постфактум ──
        if not await rt.db.claim_payment(pid, "paid"):
            await message.answer(texts.CARD_ALREADY_DONE)
            return
        await complete_payment(
            rt, bot, message.from_user.id, payment,
            success_prefix="💳 Чек получен — доступ открыт!",
        )
        for admin_id in rt.cfg.admin_ids:
            try:
                await bot.copy_message(admin_id, message.chat.id, message.message_id)
                await bot.send_message(
                    admin_id,
                    texts.CARD_AUTO_TO_ADMIN.format(
                        pid=pid,
                        title=tariff.title if tariff else payment["tariff_id"],
                        days=tariff.days if tariff else "?",
                        amount=f"{float(payment['amount']):g} ₽",
                        uid=message.from_user.id, name=name,
                    ),
                    reply_markup=card_receipt_auto_menu(pid),
                )
            except Exception as e:
                log.warning("auto receipt to admin %s: %s", admin_id, e)
        return

    for admin_id in rt.cfg.admin_ids:
        try:
            await bot.copy_message(admin_id, message.chat.id, message.message_id)
            await bot.send_message(admin_id, admin_info,
                                   reply_markup=card_receipt_admin_menu(pid))
        except Exception as e:
            log.warning("card receipt to admin %s: %s", admin_id, e)

    await message.answer(
        texts.CARD_RECEIPT_SENT,
        reply_markup=card_pay_menu(pid),
    )
    return True


@router.message(CardPayStates.waiting_receipt)
async def card_receipt_other(message: Message, state: FSMContext):
    await message.answer(texts.CARD_RECEIPT_ASK)


# ══════════════════════════ админ: решение по чеку ══════════════════════════


@router.callback_query(F.data.startswith("pc:ok:"))
async def cb_approve(query: CallbackQuery, rt: Runtime, bot: Bot):
    if not _is_admin(rt, query.from_user.id):
        return
    pid = int(query.data.rsplit(":", 1)[1])
    payment = await rt.db.get_payment(pid)
    if not payment:
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    if payment["status"] != "pending":
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    if not await rt.db.claim_payment(pid, "paid"):
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    await query.answer("Подтверждаю…")
    ok = await complete_payment(
        rt, bot, int(payment["tg_id"]), payment, success_prefix="💳 Оплата подтверждена!"
    )
    if not ok:
        await query.answer("Ошибка выдачи, платёж помечен как error", show_alert=True)
        return
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.answer(texts.CARD_APPROVED)


@router.callback_query(F.data.startswith("pc:no:"))
async def cb_reject(query: CallbackQuery, rt: Runtime, bot: Bot):
    if not _is_admin(rt, query.from_user.id):
        return
    pid = int(query.data.rsplit(":", 1)[1])
    payment = await rt.db.get_payment(pid)
    if not payment or payment["status"] != "pending":
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    await rt.db.claim_payment(pid, "canceled")
    await query.answer(texts.CARD_REJECTED_ADMIN, show_alert=True)
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await bot.send_message(int(payment["tg_id"]), texts.CARD_REJECTED.format(pid=pid))
    except Exception:
        pass


@router.callback_query(F.data.startswith("pc:verify:"))
async def cb_auto_verify(query: CallbackQuery, rt: Runtime, bot: Bot):
    """Админ подтвердил, что деньги реально поступили (пост-проверка авто-режима)."""
    if not _is_admin(rt, query.from_user.id):
        return
    pid = int(query.data.rsplit(":", 1)[1])
    payment = await rt.db.get_payment(pid)
    if not payment:
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    await rt.db.set_payment_verified(pid)
    await query.answer(texts.CARD_VERIFIED_OK, show_alert=True)
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    log.info("payment #%s verified by admin", pid)


@router.callback_query(F.data.startswith("pc:revoke:"))
async def cb_auto_revoke(query: CallbackQuery, rt: Runtime, bot: Bot):
    """Деньги не пришли — отключаем подписку пользователю."""
    if not _is_admin(rt, query.from_user.id):
        return
    pid = int(query.data.rsplit(":", 1)[1])
    payment = await rt.db.get_payment(pid)
    if not payment:
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    tg_id = int(payment["tg_id"])
    try:
        rw_user = await rt.remna.get_user_by_telegram_id(tg_id)
        if rw_user:
            await rt.remna.disable_user(rw_user["uuid"])
    except Exception as e:
        log.error("revoke subscription for %s: %s", tg_id, e)
        await query.answer(f"Ошибка отключения: {e}", show_alert=True)
        return
    await rt.db.set_payment_note(pid, "auto-approved but NOT PAID — revoked")
    await query.answer(texts.CARD_REVOKED_ADMIN, show_alert=True)
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await bot.send_message(tg_id, texts.CARD_REVOKED_USER.format(pid=pid))
    except Exception:
        pass


# ══════════════════════════ админ: настройки реквизитов ══════════════════════════


async def _card_admin_text_and_kb(rt: Runtime):
    cs = await card_settings(rt)
    enabled = await rt.db.get_setting("pay_card", "1") == "1"
    auto = await rt.db.get_setting("auto_approve_receipts", "0") == "1"
    text = texts.ADMIN_CARD_SETTINGS.format(
        status=texts.ADMIN_CARD_ON if enabled else texts.ADMIN_CARD_OFF,
        card=cs["number"] or texts.ADMIN_CARD_NOT_SET,
        bank=cs["bank"] or texts.ADMIN_CARD_NOT_SET,
        holder=cs["holder"] or texts.ADMIN_CARD_NOT_SET,
        sbp=cs["sbp"] or texts.ADMIN_CARD_NOT_SET,
        auto=texts.ADMIN_CARD_AUTO_ON if auto else texts.ADMIN_CARD_AUTO_OFF,
        auto_hint=texts.ADMIN_CARD_AUTO_HINT_ON if auto else texts.ADMIN_CARD_AUTO_HINT_OFF,
    )
    return text, admin_card_menu(enabled, bool(cs["number"]), auto)


@router.callback_query(F.data == "adm:card")
async def cb_card_menu(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.clear()  # сбросить зависший ввод, если был
    text, kb = await _card_admin_text_and_kb(rt)
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer()


@router.callback_query(F.data == "adm:card:toggle")
async def cb_card_toggle(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    current = await rt.db.get_setting("pay_card", "1") == "1"
    await rt.db.set_setting("pay_card", "0" if current else "1")
    text, kb = await _card_admin_text_and_kb(rt)
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer("Сохранено")


@router.callback_query(F.data == "adm:card:auto")
async def cb_card_auto(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    current = await rt.db.get_setting("auto_approve_receipts", "0") == "1"
    await rt.db.set_setting("auto_approve_receipts", "0" if current else "1")
    text, kb = await _card_admin_text_and_kb(rt)
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer("Сохранено")


@router.callback_query(F.data == "adm:card:del")
async def cb_card_del(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    for key in ("card_number", "card_bank", "card_holder"):
        await rt.db.set_setting(key, "")
    text, kb = await _card_admin_text_and_kb(rt)
    await query.message.edit_text(text, reply_markup=kb)
    await query.answer(texts.ADMIN_CARD_CLEARED, show_alert=True)


FIELD_TO_STATE = {
    "num": "number",
    "bank": "bank",
    "holder": "holder",
    "sbp": "sbp",
}


@router.callback_query(F.data.startswith("adm:card:set:"))
async def cb_card_set(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    field = query.data.rsplit(":", 1)[1]
    if field not in FIELD_TO_STATE:
        await query.answer("Неизвестное поле", show_alert=True)
        return
    prompts = {
        "num": texts.ADMIN_CARD_ASK_NUM,
        "bank": texts.ADMIN_CARD_ASK_BANK,
        "holder": texts.ADMIN_CARD_ASK_HOLDER,
        "sbp": texts.ADMIN_CARD_ASK_SBP,
    }
    await state.set_state(getattr(CardSettingsStates, FIELD_TO_STATE[field]))
    await query.message.answer(
        prompts[field], reply_markup=admin_back()
    )
    await query.answer()


@router.message(CardSettingsStates.number)
async def card_num_input(message: Message, state: FSMContext, rt: Runtime):
    value = (message.text or "").strip()
    await state.clear()
    if value.lower() == "/cancel":
        return await message.answer("Отменено.", reply_markup=admin_back())
    # выкидываем ВСЁ, кроме цифр: пробелы, дефисы, неразрывные пробелы при копипасте
    digits = re.sub(r"\D", "", value)
    if not (12 <= len(digits) <= 20):
        await message.answer(
            "Похоже, это не номер карты — нужно 12–20 цифр.\n"
            "Можно с пробелами или дефисами, например: 2200 1234 5678 9010",
        )
        await state.set_state(CardSettingsStates.number)
        return
    formatted = " ".join(digits[i:i + 4] for i in range(0, len(digits), 4))
    await rt.db.set_setting("card_number", formatted)
    await message.answer(
        texts.ADMIN_CARD_SET_OK + f"\n💳 <code>{formatted}</code>",
        reply_markup=admin_back(),
    )


@router.message(CardSettingsStates.bank)
async def card_bank_input(message: Message, state: FSMContext, rt: Runtime):
    value = (message.text or "").strip()
    await state.clear()
    if value.lower() == "/cancel":
        return await message.answer("Отменено.")
    await rt.db.set_setting("card_bank", value[:64])
    await message.answer(texts.ADMIN_CARD_SET_OK, reply_markup=admin_back())


@router.message(CardSettingsStates.holder)
async def card_holder_input(message: Message, state: FSMContext, rt: Runtime):
    value = (message.text or "").strip()
    await state.clear()
    if value.lower() == "/cancel":
        return await message.answer("Отменено.")
    await rt.db.set_setting("card_holder", value[:64])
    await message.answer(texts.ADMIN_CARD_SET_OK, reply_markup=admin_back())


@router.message(CardSettingsStates.sbp)
async def card_sbp_input(message: Message, state: FSMContext, rt: Runtime):
    value = (message.text or "").strip()
    await state.clear()
    if value.lower() == "/cancel":
        return await message.answer("Отменено.")
    if value == "0":
        await rt.db.set_setting("card_sbp", "")
        return await message.answer("🗑 СБП убран из реквизитов.", reply_markup=admin_back())
    digits = re.sub(r"\D", "", value)
    if not (10 <= len(digits) <= 15):
        await message.answer("Нужен номер телефона, например +79001234567 (или 0 — убрать):")
        await state.set_state(CardSettingsStates.sbp)
        return
    await rt.db.set_setting("card_sbp", value)
    await message.answer(texts.ADMIN_CARD_SET_OK, reply_markup=admin_back())
