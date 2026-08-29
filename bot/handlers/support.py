"""Техподдержка: тикеты пользователей и ответы администраторов через бота."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .. import texts
from ..keyboards import (
    admin_back,
    back_to_menu,
    ticket_admin_menu,
    ticket_user_menu,
    tickets_list_menu,
)
from ..services import Runtime
from ..utils import fmt_date, parse_iso

router = Router(name="support")
log = logging.getLogger(__name__)

MEDIA_TYPES = {"text", "photo", "video", "document", "voice", "audio"}


class SupportStates(StatesGroup):
    waiting_message = State()


class SupportAdminStates(StatesGroup):
    reply = State()


def _is_admin(rt: Runtime, user_id: int) -> bool:
    return user_id in rt.cfg.admin_ids


# ══════════════════════════ сторона пользователя ══════════════════════════


async def _relay_to_admins(rt: Runtime, bot: Bot, message: Message, ticket_id: int) -> None:
    """Пересылает сообщение пользователя всем админам + кнопки ответа."""
    bot_user = await rt.db.get_bot_user(message.from_user.id) or {}
    name = bot_user.get("first_name") or message.from_user.username or str(message.from_user.id)
    for admin_id in rt.cfg.admin_ids:
        try:
            await bot.copy_message(admin_id, message.chat.id, message.message_id)
            await bot.send_message(
                admin_id,
                texts.SUPPORT_MSG_TO_ADMINS.format(
                    tid=ticket_id, uid=message.from_user.id, name=name,
                ),
                reply_markup=ticket_admin_menu(ticket_id, answered=False),
            )
        except Exception as e:
            log.warning("ticket relay to admin %s: %s", admin_id, e)


@router.callback_query(F.data == "support")
async def cb_support(query: CallbackQuery, state: FSMContext, rt: Runtime):
    await state.clear()
    ticket = await rt.db.open_ticket_for_user(query.from_user.id)
    if ticket:
        status = "ожидает ответа" if ticket["status"] == "open" else "получен ответ"
        await query.message.edit_text(
            texts.SUPPORT_TICKET_STATUS.format(tid=ticket["id"], status=status),
            reply_markup=ticket_user_menu(ticket["id"]),
        )
        await query.answer()
        return
    await state.set_state(SupportStates.waiting_message)
    await query.message.edit_text(
        texts.SUPPORT_INTRO,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=back_to_menu()),
    )
    await query.answer()


@router.message(SupportStates.waiting_message)
async def support_first_message(message: Message, state: FSMContext, rt: Runtime, bot: Bot):
    await state.clear()
    if (message.text or "").startswith("/cancel"):
        await message.answer("Отменено.")
        return
    ticket_id = await rt.db.create_ticket(message.from_user.id)
    await rt.db.add_ticket_message(
        ticket_id, "user", message.from_user.id, message.chat.id, message.message_id
    )
    await _relay_to_admins(rt, bot, message, ticket_id)
    await message.answer(
        texts.SUPPORT_TICKET_CREATED.format(tid=ticket_id),
        reply_markup=ticket_user_menu(ticket_id),
    )


@router.callback_query(F.data.startswith("tk:close:"))
async def cb_user_close(query: CallbackQuery, rt: Runtime, bot: Bot):
    ticket = await rt.db.get_ticket(int(query.data.rsplit(":", 1)[1]))
    if not ticket or ticket["tg_id"] != query.from_user.id:
        await query.answer(texts.SUPPORT_USER_NOT_FOUND_TICKET, show_alert=True)
        return
    await rt.db.set_ticket_status(ticket["id"], "closed")
    await query.message.edit_text(
        texts.SUPPORT_TICKET_CLOSED_BY_USER.format(tid=ticket["id"])
    )
    await query.answer()
    for admin_id in rt.cfg.admin_ids:
        try:
            await bot.send_message(
                admin_id, f"🎫 Обращение #{ticket['id']} закрыл пользователь."
            )
        except Exception:
            pass


# ══════════════════════════ сторона админа ══════════════════════════


@router.callback_query(F.data == "adm:tickets")
async def cb_tickets(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    tickets = await rt.db.open_tickets()
    if not tickets:
        await query.message.edit_text(
            texts.ADMIN_TICKETS.format(list=texts.ADMIN_TICKETS_EMPTY),
            reply_markup=admin_back(),
        )
    else:
        lines = "".join(
            f"├ #{t['id']} — от <code>{t['tg_id']}</code>, "
            f"{'получен ответ' if t['status'] == 'answered' else 'ожидает ответа'}\n"
            for t in tickets
        )
        await query.message.edit_text(
            texts.ADMIN_TICKETS.format(list=lines), reply_markup=tickets_list_menu(tickets)
        )
    await query.answer()


@router.callback_query(F.data.startswith("adm:tk:reply:"))
async def cb_admin_reply(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    tid = int(query.data.rsplit(":", 1)[1])
    await state.set_state(SupportAdminStates.reply)
    await state.update_data(tid=tid)
    await query.message.answer(texts.ADMIN_TICKET_REPLY_ASK)
    await query.answer()


@router.message(SupportAdminStates.reply)
async def admin_reply_message(message: Message, state: FSMContext, rt: Runtime, bot: Bot):
    data = await state.get_data()
    await state.clear()
    tid = data.get("tid")
    ticket = await rt.db.get_ticket(tid) if tid else None
    if not ticket or ticket["status"] == "closed":
        await message.answer(texts.SUPPORT_USER_NOT_FOUND_TICKET)
        return
    try:
        await bot.copy_message(ticket["tg_id"], message.chat.id, message.message_id)
    except Exception as e:
        await message.answer(f"❌ Не удалось доставить: {e}")
        return
    await rt.db.add_ticket_message(
        tid, "admin", message.from_user.id, message.chat.id, message.message_id
    )
    await rt.db.set_ticket_status(tid, "answered")
    await message.answer(texts.SUPPORT_ADMIN_REPLY_SENT)
    try:
        await bot.send_message(
            ticket["tg_id"], f"💬 <b>Ответ поддержки (обращение #{tid}):</b>"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm:tk:close:"))
async def cb_admin_close(query: CallbackQuery, rt: Runtime, bot: Bot):
    if not _is_admin(rt, query.from_user.id):
        return
    tid = int(query.data.rsplit(":", 1)[1])
    ticket = await rt.db.get_ticket(tid)
    if not ticket:
        await query.answer(texts.SUPPORT_USER_NOT_FOUND_TICKET, show_alert=True)
        return
    await rt.db.set_ticket_status(tid, "closed")
    await query.answer("Закрыто")
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await bot.send_message(
            ticket["tg_id"], texts.SUPPORT_TICKET_CLOSED_BY_ADMIN.format(tid=tid)
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm:tk:"))
async def cb_admin_ticket(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    raw = query.data.split(":")[2]
    if not raw.isdigit():
        await query.answer()
        return
    ticket = await rt.db.get_ticket(int(raw))
    if not ticket:
        await query.answer(texts.SUPPORT_USER_NOT_FOUND_TICKET, show_alert=True)
        return
    created = parse_iso(ticket["created_at"])
    status_str = (
        "ожидает ответа" if ticket["status"] == "open"
        else "получен ответ" if ticket["status"] == "answered"
        else "закрыто"
    )
    await query.message.answer(
        texts.ADMIN_TICKET_DETAIL.format(
            tid=ticket["id"], status=status_str,
            uid=ticket["tg_id"], name=ticket["tg_id"],
            created=fmt_date(created, rt.cfg.tz),
        ),
        reply_markup=ticket_admin_menu(ticket["id"], ticket["status"] == "answered"),
    )
    await query.answer()


@router.message(F.content_type.in_(MEDIA_TYPES))
async def support_followup(message: Message, rt: Runtime, bot: Bot):
    """Фолбэк для свободных сообщений (регистрируется последним).

    1) pending-оплата картой -> обрабатываем как чек (даже после рестарта бота);
    2) открытый тикет -> пересылаем админам;
    3) иначе — молча игнорируем.
    """
    if (message.text or "").startswith("/"):
        return
    if _is_admin(rt, message.from_user.id):
        return  # сообщения админов обрабатывают FSM-хэндлеры выше
    from .pay_card import process_card_receipt

    if await process_card_receipt(rt, bot, message):
        return
    ticket = await rt.db.open_ticket_for_user(message.from_user.id)
    if ticket is None:
        return
    await rt.db.add_ticket_message(
        ticket["id"], "user", message.from_user.id, message.chat.id, message.message_id
    )
    await _relay_to_admins(rt, bot, message, ticket["id"])
    await message.answer("📨 Передано в поддержку.")
