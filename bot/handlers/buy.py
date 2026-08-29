"""Покупка подписки и все платёжные хэндлеры (Stars, CryptoBot, ЮKassa)."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from .. import texts
from ..keyboards import card_pay_menu, pay_link_menu, pay_methods_menu, tariffs_menu
from ..payments import ProviderError
from ..services import Runtime, card_settings, complete_payment

router = Router(name="buy")
log = logging.getLogger(__name__)


@router.callback_query(F.data == "buy")
async def cb_buy(query: CallbackQuery, rt: Runtime):
    tariffs = list(rt.cfg.tariffs.values())
    await query.message.edit_text(texts.MENU_BUY, reply_markup=tariffs_menu(tariffs))
    await query.answer()


@router.callback_query(F.data.startswith("tar:"))
async def cb_tariff(query: CallbackQuery, rt: Runtime):
    tariff_id = query.data.split(":", 1)[1]
    tariff = rt.cfg.tariffs.get(tariff_id)
    if tariff is None:
        await query.answer("Тариф не найден", show_alert=True)
        return
    providers = await rt.available_providers(tariff)
    if not any(providers.values()):
        reasons = await rt.unavailable_reasons(tariff)
        is_admin = query.from_user.id in rt.cfg.admin_ids
        text = (
            texts.PAYMENTS_NOTHING.format(reasons="".join(reasons))
            if is_admin
            else texts.PAYMENTS_NOTHING.format(reasons="")
        )
        await query.message.edit_text(text)
        await query.answer()
        return
    desc = f"{tariff.description}\n" if tariff.description else ""
    await query.message.edit_text(
        texts.TARIFF_CARD.format(
            title=tariff.title,
            days=tariff.days,
            description=desc,
            price=tariff.price_line(),
        ),
        reply_markup=pay_methods_menu(tariff, providers),
    )
    await query.answer()


# ─────────────────────────── Telegram Stars ───────────────────────────


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(query: CallbackQuery, state: FSMContext, rt: Runtime, bot: Bot):
    _, tariff_id, provider = query.data.split(":", 2)
    tariff = rt.cfg.tariffs.get(tariff_id)
    if tariff is None:
        await query.answer("Тариф не найден", show_alert=True)
        return
    tg_id = query.from_user.id

    if provider == "card":
        if not tariff.price_rub:
            await query.answer("Оплата переводом недоступна для тарифа", show_alert=True)
            return
        cs = await card_settings(rt)
        if not cs["number"]:
            await query.answer("Реквизиты не настроены, выберите другой способ", show_alert=True)
            return
        payment_id = await rt.db.add_payment(
            tg_id, tariff.id, "card", f"{tariff.price_rub:.2f}", "RUB"
        )
        from .pay_card import CardPayStates, _card_text

        await state.set_state(CardPayStates.waiting_receipt)
        await state.update_data(pid=payment_id)
        await query.message.edit_text(
            await _card_text(rt, tariff, tariff.price_rub),
            reply_markup=card_pay_menu(payment_id),
        )
        await query.answer()

    elif provider == "stars":
        if not tariff.price_stars:
            await query.answer("Оплата звёздами недоступна", show_alert=True)
            return
        payment_id = await rt.db.add_payment(
            tg_id, tariff.id, "stars", str(tariff.price_stars), "XTR"
        )
        await bot.send_invoice(
            chat_id=tg_id,
            title=tariff.title,
            description=f"Доступ на {tariff.days} дн.",
            payload=str(payment_id),
            currency="XTR",
            prices=[LabeledPrice(label=tariff.title, amount=tariff.price_stars)],
        )
        await query.answer()

    elif provider == "cryptobot":
        if not (rt.cryptobot and tariff.price_usdt):
            await query.answer("Оплата криптой недоступна", show_alert=True)
            return
        try:
            invoice = await rt.cryptobot.create_invoice(
                amount=tariff.price_usdt,
                description=f"{tariff.title} — доступ на {tariff.days} дн.",
                payload=f"{tg_id}:{tariff.id}",
            )
        except ProviderError as e:
            log.error("cryptobot create_invoice: %s", e)
            await query.answer(f"Ошибка платёжной системы: {e}", show_alert=True)
            return
        url = rt.cryptobot.pay_url(invoice)
        payment_id = await rt.db.add_payment(
            tg_id, tariff.id, "cryptobot", f"{tariff.price_usdt:.2f}", "USDT",
            ext_id=str(invoice.get("invoice_id")),
        )
        await query.message.edit_text(
            texts.PAYMENT_CREATED.format(
                title=tariff.title, days=tariff.days,
                amount=f"{tariff.price_usdt:g} USDT", hint=texts.PAY_LINK_HINT,
            ),
            reply_markup=pay_link_menu(url, payment_id) if url else None,
        )
        await query.answer()

    elif provider == "yookassa":
        if not (rt.yookassa and tariff.price_rub):
            await query.answer("Оплата картой недоступна", show_alert=True)
            return
        try:
            payment = await rt.yookassa.create_payment(
                amount_rub=tariff.price_rub,
                description=f"{tariff.title} — доступ на {tariff.days} дн.",
                return_url=f"https://t.me/{rt.bot_username}",
                metadata=f"{tg_id}:{tariff.id}",
            )
        except ProviderError as e:
            log.error("yookassa create_payment: %s", e)
            await query.answer(f"Ошибка платёжной системы: {e}", show_alert=True)
            return
        url = rt.yookassa.confirmation_url(payment)
        payment_id = await rt.db.add_payment(
            tg_id, tariff.id, "yookassa", f"{tariff.price_rub:.2f}", "RUB",
            ext_id=str(payment.get("id")),
        )
        await query.message.edit_text(
            texts.PAYMENT_CREATED.format(
                title=tariff.title, days=tariff.days,
                amount=f"{tariff.price_rub:g} ₽", hint=texts.PAY_LINK_HINT,
            ),
            reply_markup=pay_link_menu(url, payment_id) if url else None,
        )
        await query.answer()
    else:
        await query.answer("Неизвестный способ оплаты", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, rt: Runtime):
    payment = await rt.db.get_payment(int(query.invoice_payload)) if query.invoice_payload.isdigit() else None
    if payment is None or payment["status"] != "pending":
        await query.answer(ok=False, error_message=texts.PAYMENT_NOT_FOUND)
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, rt: Runtime, bot: Bot):
    sp = message.successful_payment
    payment = await rt.db.get_payment(int(sp.invoice_payload)) if sp.invoice_payload.isdigit() else None
    if payment is None or int(payment["tg_id"]) != message.from_user.id:
        log.warning("successful_payment with unknown payload: %s", sp.invoice_payload)
        return
    if await rt.db.claim_payment(payment["id"], "paid"):
        await complete_payment(rt, bot, message.from_user.id, payment,
                               success_prefix=texts.SUCCESS_STARS)


# ─────────────────── проверка / отмена внешних счетов ───────────────────


async def _check_external(rt: Runtime, payment: dict) -> str | None:
    """Возвращает 'paid' | 'active' | 'canceled' | None (ошибка)."""
    provider = payment["provider"]
    try:
        if provider == "cryptobot" and rt.cryptobot:
            status = await rt.cryptobot.check_invoice(payment["ext_id"])
            return {"paid": "paid", "active": "active", "expired": "canceled"}.get(status, "active")
        if provider == "yookassa" and rt.yookassa:
            status = await rt.yookassa.check_payment(payment["ext_id"])
            return {"paid": "paid", "pending": "active", "canceled": "canceled"}.get(status, "active")
    except ProviderError as e:
        log.error("check %s %s: %s", provider, payment["ext_id"], e)
        return None
    return None


@router.callback_query(F.data.startswith("chk:"))
async def cb_check(query: CallbackQuery, rt: Runtime, bot: Bot):
    raw = query.data.split(":", 1)[1]
    payment = await rt.db.get_payment(int(raw)) if raw.isdigit() else None
    if not payment or int(payment["tg_id"]) != query.from_user.id:
        await query.answer(texts.PAYMENT_NOT_FOUND, show_alert=True)
        return
    if payment["status"] != "pending":
        await query.answer(texts.PAYMENT_NOT_FOUND, show_alert=True)
        return
    status = await _check_external(rt, payment)
    if status is None:
        await query.answer("Платёжная система недоступна, попробуйте позже", show_alert=True)
        return
    if status == "paid":
        await query.answer("✅ Оплата найдена!")
        if await rt.db.claim_payment(payment["id"], "paid"):
            await complete_payment(rt, bot, query.from_user.id, payment)
        return
    if status == "canceled":
        await rt.db.claim_payment(payment["id"], "canceled")
        await query.answer(texts.PAYMENT_EXPIRED, show_alert=True)
        return
    await query.answer(texts.PAYMENT_STILL_PENDING, show_alert=True)


@router.callback_query(F.data.startswith("cxl:"))
async def cb_cancel_invoice(query: CallbackQuery, rt: Runtime):
    raw = query.data.split(":", 1)[1]
    payment = await rt.db.get_payment(int(raw)) if raw.isdigit() else None
    if not payment or int(payment["tg_id"]) != query.from_user.id:
        await query.answer(texts.PAYMENT_NOT_FOUND, show_alert=True)
        return
    if not await rt.db.claim_payment(payment["id"], "canceled"):
        await query.answer(texts.PAYMENT_NOT_FOUND, show_alert=True)
        return
    await query.message.edit_text(texts.PAYMENT_CANCELED)
    await query.answer()
