"""Оплата переводом на карту: чек от пользователя → подтверждение админом → выдача."""
from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..keyboards import (admin_back, admin_card_menu, admin_menu, card_pay_menu,
                         card_reject_reasons_menu, card_receipt_admin_menu,
                         card_receipt_auto_menu, card_admin_detail_menu,
                         cards_admin_menu)
from ..services import (Runtime, active_pay_cards, complete_payment,
                         migrate_single_card, sys_log)

router = Router(name="pay-card")
log = logging.getLogger(__name__)

RECEIPT_TYPES = {"photo", "document", "video", "text", "voice", "audio"}


class CardPayStates(StatesGroup):
    waiting_receipt = State()


class CardAddFSM(StatesGroup):
    bank = State()
    number = State()
    holder = State()
    sbp = State()


class CardRejectStates(StatesGroup):
    reason = State()


class CardSettingsStates(StatesGroup):
    number = State()
    bank = State()
    holder = State()
    sbp = State()


def _is_admin(rt: Runtime, user_id: int) -> bool:
    return user_id in rt.cfg.admin_ids


async def _can_confirm(rt: Runtime, user_id: int) -> bool:
    """Админ или оператор оплаты."""
    return await rt.is_payment_operator(user_id)


async def _card_text(rt: Runtime, tariff, card: dict, smart: float) -> str:
    holder_line = (
        texts.CARD_HOLDER_LINE.format(holder=card["holder"]) if card.get("holder") else ""
    )
    sbp_line = (
        texts.CARD_SBP_LINE.format(sbp=card["sbp"]) if card.get("sbp") else ""
    )
    smart_on = await rt.db.get_setting("smart_sum", "1") == "1"
    hint = texts.CARD_SMART_HINT if smart_on else ""
    return texts.CARD_PAY_TEXT.format(
        title=tariff.title, days=tariff.days,
        smart=f"{smart:.2f} ₽", smart_hint=hint,
        bank=card["bank"], card=card["number"],
        holder_line=holder_line, sbp_line=sbp_line,
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
    pay_amount = float(payment["smart_amount"] or payment["amount"] or 0)
    amount_str = f"{pay_amount:g}"
    admin_info = texts.CARD_TO_ADMIN.format(
        pid=pid,
        title=tariff.title if tariff else payment["tariff_id"],
        days=tariff.days if tariff else "?",
        amount=f"{amount_str} ₽",
        uid=message.from_user.id, name=name,
    )

    auto = await rt.db.get_setting("auto_approve_receipts", "0") == "1"
    if auto:
        # ── доверительный режим: выдаём подписку сразу, админ проверяет постфактум ──
        if not await rt.db.claim_payment(pid, "paid"):
            await message.answer(texts.CARD_ALREADY_DONE)
            return
        delivered = await complete_payment(
            rt, bot, message.from_user.id, payment,
            success_prefix="💳 Чек получен — доступ открыт!",
        )
        if not delivered:
            # выдача не удалась: юзеру и админам уже ушли ошибки, платёж помечен error
            for admin_id in rt.cfg.admin_ids:
                try:
                    await bot.send_message(
                        admin_id,
                        f"⚠️ Автоподтверждение #{pid}: оплата принята, но выдача не удалась "
                        f"(см. логи). После исправления выдайте вручную: /admin → 🎁",
                    )
                except Exception:
                    pass
            return
        for admin_id in await rt.payment_recipients():
            try:
                await bot.copy_message(admin_id, message.chat.id, message.message_id)
                await bot.send_message(
                    admin_id,
                    texts.CARD_AUTO_TO_ADMIN.format(
                        pid=pid,
                        title=tariff.title if tariff else payment["tariff_id"],
                        days=tariff.days if tariff else "?",
                        amount=f"{amount_str} ₽",
                        uid=message.from_user.id, name=name,
                    ),
                    reply_markup=card_receipt_auto_menu(pid),
                )
            except Exception as e:
                log.warning("auto receipt to admin %s: %s", admin_id, e)
        return

    for admin_id in await rt.payment_recipients():
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
    if not await _can_confirm(rt, query.from_user.id):
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
async def cb_reject(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not await _can_confirm(rt, query.from_user.id):
        return
    pid = int(query.data.rsplit(":", 1)[1])
    payment = await rt.db.get_payment(pid)
    if not payment or payment["status"] != "pending":
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    await query.message.edit_reply_markup(
        reply_markup=card_reject_reasons_menu(pid)
    )
    await query.answer()


@router.callback_query(F.data.startswith("pc:no2:"))
async def cb_reject_with_reason(query: CallbackQuery, state: FSMContext, rt: Runtime, bot: Bot):
    if not await _can_confirm(rt, query.from_user.id):
        return
    _, _, pid_raw, code = query.data.split(":")
    pid = int(pid_raw)
    payment = await rt.db.get_payment(pid)
    if not payment or payment["status"] != "pending":
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    if code == "custom":
        await state.set_state(CardRejectStates.reason)
        await state.update_data(pid=pid)
        await query.message.answer(texts.CARD_REJECT_CUSTOM_ASK)
        await query.answer()
        return
    reason = texts.CARD_REJECT_REASONS.get(code, "—")
    await _do_reject(rt, bot, query, payment, reason)


@router.message(CardRejectStates.reason)
async def reject_custom_reason(message: Message, state: FSMContext, rt: Runtime, bot: Bot):
    reason = (message.text or "").strip()
    data = await state.get_data()
    await state.clear()
    pid = data.get("pid")
    payment = await rt.db.get_payment(pid) if pid else None
    if not payment or payment["status"] != "pending":
        await message.answer(texts.CARD_ALREADY_DONE)
        return
    if not reason or reason.startswith("/"):
        await message.answer("Отменено.")
        return
    await _do_reject(rt, bot, message, payment, reason[:400], answer=False)


async def _do_reject(rt: Runtime, bot: Bot, query_or_msg, payment: dict,
                     reason: str, *, answer: bool = True):
    pid = payment["id"]
    await rt.db.claim_payment(pid, "canceled")
    await rt.db.set_payment_note(pid, f"rejected: {reason[:200]}")
    try:
        await bot.send_message(
            int(payment["tg_id"]),
            texts.CARD_REJECT_USER.format(pid=pid, reason=reason),
        )
    except Exception:
        pass
    if isinstance(query_or_msg, CallbackQuery):
        if answer:
            await query_or_msg.answer(texts.CARD_REJECTED_ADMIN, show_alert=True)
        try:
            await query_or_msg.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            await query_or_msg.message.answer(texts.CARD_REJECTED_ADMIN)
        except Exception:
            pass
    else:
        await query_or_msg.answer(texts.CARD_REJECTED_ADMIN, reply_markup=admin_back())


# повторный показ реквизитов (из напоминания)
@router.callback_query(F.data.startswith("pc:show:"))
async def cb_show_details(query: CallbackQuery, rt: Runtime):
    pid = int(query.data.rsplit(":", 1)[1])
    payment = await rt.db.get_payment(pid)
    if not payment or int(payment["tg_id"]) != query.from_user.id:
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    if payment["status"] != "pending":
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    tariff = rt.cfg.tariffs.get(payment["tariff_id"])
    if tariff is None:
        await query.answer(texts.CARD_ALREADY_DONE, show_alert=True)
        return
    card_id = payment.get("card_id")
    card = await rt.db.get_pay_card(card_id) if card_id else None
    if card is None:
        cards = await active_pay_cards(rt)
        card = cards[0] if cards else None
    if card is None:
        await query.answer("Карты недоступны, напишите в поддержку", show_alert=True)
        return
    smart = float(payment["smart_amount"]) if payment.get("smart_amount") else (
        float(payment["amount"]) if payment["amount"] else (tariff.price_rub or 0)
    )
    await query.message.answer(
        await _card_text(rt, tariff, card, smart),
        reply_markup=card_pay_menu(pid),
    )
    await query.answer()


@router.callback_query(F.data.startswith("pc:verify:"))
async def cb_auto_verify(query: CallbackQuery, rt: Runtime, bot: Bot):
    """Оператор/админ подтвердил поступление денег (пост-проверка авто-режима)."""
    if not await _can_confirm(rt, query.from_user.id):
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
    if not await _can_confirm(rt, query.from_user.id):
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
    await sys_log(rt, bot, texts.SYS_CARD_DECISION.format(
        icon="🚫", pid=pid, decision="отменена (деньги не поступили)",
        by=query.from_user.id, reason="не оплатил",
    ))


# ══════════════════════════ админ: настройки реквизитов ══════════════════════════


async def _card_admin_text_and_kb(rt: Runtime):
    enabled = await rt.db.get_setting("pay_card", "1") == "1"
    smart = await rt.db.get_setting("smart_sum", "1") == "1"
    cards = await rt.db.pay_cards()
    if cards:
        lines = "".join(
            texts.ADMIN_CARD_LIST_LINE.format(
                enabled=texts.ADMIN_CARD_ON_MARK if c["enabled"] else texts.ADMIN_CARD_OFF_MARK,
                bank=c["bank"], number=c["number"],
                sbp_mark=texts.ADMIN_CARD_SBP_MARK if c["sbp"] else "",
            )
            for c in cards
        )
    else:
        lines = texts.ADMIN_CARDS_EMPTY + "\n"
    auto = await rt.db.get_setting("auto_approve_receipts", "0") == "1"
    text = texts.ADMIN_CARD_SETTINGS.format(
        status=texts.ADMIN_CARD_ON if enabled else texts.ADMIN_CARD_OFF,
        smart=texts.SMART_SUM_ON if smart else texts.SMART_SUM_OFF,
        cards_list=lines,
    ) + (
        "\n⚙️ Автоподтверждение чеков: "
        + (texts.ADMIN_CARD_AUTO_ON if auto else texts.ADMIN_CARD_AUTO_OFF)
    )
    return text, admin_card_menu(enabled, bool(cards), auto)


@router.callback_query(F.data == "adm:card")
async def cb_card_menu(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.clear()  # сбросить зависший ввод, если был
    await migrate_single_card(rt)
    cards = await rt.db.pay_cards()
    text = (await _card_admin_text_and_kb(rt))[0]
    await query.message.edit_text(text, reply_markup=cards_admin_menu(cards))
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


# ══════════════════════════ управление картами ══════════════════════════


@router.callback_query(F.data.startswith("adm:card2:info:"))
async def cb_card2_info(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    card = await rt.db.get_pay_card(int(query.data.rsplit(":", 1)[1]))
    if not card:
        await query.answer("Карта не найдена", show_alert=True)
        return
    await query.message.edit_text(
        texts.ADMIN_CARD_DETAIL.format(
            bank=card["bank"], number=card["number"],
            holder=card["holder"] or "—", sbp=card["sbp"] or "—",
            status=(texts.ADMIN_CARD_ON if card["enabled"] else texts.ADMIN_CARD_OFF),
        ),
        reply_markup=card_admin_detail_menu(card),
    )
    await query.answer()


@router.callback_query(F.data.startswith("adm:card2:tgl:"))
async def cb_card2_toggle(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    card = await rt.db.get_pay_card(int(query.data.rsplit(":", 1)[1]))
    if not card:
        await query.answer("Карта не найдена", show_alert=True)
        return
    if card["enabled"]:
        enabled_cards = await rt.db.pay_cards(only_enabled=True)
        if len(enabled_cards) <= 1:
            return await query.answer(texts.ADMIN_CARD_LAST, show_alert=True)
    await rt.db.set_pay_card_enabled(card["id"], not card["enabled"])
    await cb_card2_info(query, rt)


@router.callback_query(F.data.startswith("adm:card2:del:"))
async def cb_card2_delete(query: CallbackQuery, rt: Runtime, state: FSMContext):
    if not _is_admin(rt, query.from_user.id):
        return
    await rt.db.delete_pay_card(int(query.data.rsplit(":", 1)[1]))
    await query.answer(texts.ADMIN_CARD_DELETED, show_alert=True)
    await cb_card_menu(query, state, rt)


@router.callback_query(F.data == "adm:card2:smart")
async def cb_card2_smart(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    current = await rt.db.get_setting("smart_sum", "1") == "1"
    await rt.db.set_setting("smart_sum", "0" if current else "1")
    await query.answer("Сохранено")
    text = (await _card_admin_text_and_kb(rt))[0]
    cards = await rt.db.pay_cards()
    try:
        await query.message.edit_text(text, reply_markup=cards_admin_menu(cards))
    except Exception:
        pass


@router.callback_query(F.data == "adm:card2:add")
async def cb_card2_add(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.set_state(CardAddFSM.bank)
    await query.message.edit_text(texts.ADMIN_CARD_ASK_BANK2)
    await query.answer()


@router.message(CardAddFSM.bank)
async def card2_bank_input(message: Message, state: FSMContext, rt: Runtime):
    value = (message.text or "").strip()
    if value.lower() == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=admin_menu())
    if not (1 <= len(value) <= 48):
        await message.answer("Название банка 1–48 символов:")
        return
    await state.update_data(bank=value)
    await state.set_state(CardAddFSM.number)
    await message.answer(texts.ADMIN_CARD_ASK_NUM)


@router.message(CardAddFSM.number)
async def card2_number_input(message: Message, state: FSMContext, rt: Runtime):
    value = (message.text or "").strip()
    digits = re.sub(r"\D", "", value)
    if not (12 <= len(digits) <= 20):
        await message.answer(
            "Нужно 12–20 цифр. Можно с пробелами/дефисами, например: 2200 1234 5678 9010"
        )
        return
    await state.update_data(number=digits)
    await state.set_state(CardAddFSM.holder)
    await message.answer(texts.ADMIN_CARD_ASK_HOLDER)


@router.message(CardAddFSM.holder)
async def card2_holder_input(message: Message, state: FSMContext, rt: Runtime):
    value = (message.text or "").strip()
    if value.lower() == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=admin_menu())
    if value == "-":
        value = ""
    await state.update_data(holder=value[:64])
    await state.set_state(CardAddFSM.sbp)
    await message.answer(texts.ADMIN_CARD_ASK_SBP)


@router.message(CardAddFSM.sbp)
async def card2_sbp_input(message: Message, state: FSMContext, rt: Runtime):
    value = (message.text or "").strip()
    data = await state.get_data()
    await state.clear()
    if value.lower() == "/cancel":
        return await message.answer("Отменено.", reply_markup=admin_menu())
    sbp = ""
    if value not in ("-", "0"):
        digits = re.sub(r"\D", "", value)
        if digits and 10 <= len(digits) <= 15:
            sbp = value
    await rt.db.add_pay_card(
        bank=data.get("bank", "Банк"),
        number=data.get("number", ""),
        holder=data.get("holder", ""),
        sbp=sbp,
    )
    await message.answer(
        texts.ADMIN_CARD_ADDED.format(bank=data.get("bank", "")),
        reply_markup=admin_menu(),
    )
