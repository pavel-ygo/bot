"""Админ-раздел: статистика, ноды, рассылка, выдача подписок, вкл/выкл юзеров."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..keyboards import admin_back, admin_confirm_broadcast, admin_menu
from ..payments import ProviderError
from ..remnawave import RemnaError
from ..services import Runtime, deliver_subscription, subscription_kb
from ..utils import fmt_date, parse_iso

router = Router(name="admin")
log = logging.getLogger(__name__)


class AdminStates(StatesGroup):
    broadcast_message = State()
    grant_target = State()
    grant_days = State()
    ban_target = State()


def _is_admin(rt: Runtime, user_id: int) -> bool:
    return user_id in rt.cfg.admin_ids


@router.message(Command("admin"))
async def cmd_admin(message: Message, rt: Runtime):
    if not _is_admin(rt, message.from_user.id):
        return
    await message.answer(texts.ADMIN_MENU, reply_markup=admin_menu())


@router.callback_query(F.data == "adm:main")
async def cb_admin(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        await query.answer("⛔️ Только для администраторов", show_alert=True)
        return
    await query.message.edit_text(texts.ADMIN_MENU, reply_markup=admin_menu())
    await query.answer()


@router.callback_query(F.data == "adm:cancel")
async def cb_admin_cancel(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.clear()
    await query.message.edit_text("Отменено.", reply_markup=admin_menu())
    await query.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, message.from_user.id):
        return
    if await state.get_state() is not None:
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_menu())


# ─────────────────────────── статистика ───────────────────────────


def _fmt_stats(rt: Runtime, db_stats: dict, rw: dict) -> str:
    if db_stats["by_provider"]:
        lines = []
        for row in db_stats["by_provider"]:
            icon = {"stars": "⭐", "cryptobot": "🪙", "yookassa": "💳"}.get(row["provider"], "💰")
            cur = {"XTR": "⭐", "RUB": "₽", "USDT": "USDT"}.get(row["currency"], row["currency"])
            lines.append(f"├ {icon} {row['provider']}: <b>{row['cnt']}</b> шт / {row['total']:g} {cur}")
        sales = "\n".join(lines) + "\n"
    else:
        sales = f"├ {texts.ADMIN_STATS_EMPTY}\n"
    return texts.ADMIN_STATS.format(
        bot_users=db_stats["bot_users"],
        sales=sales,
        week=db_stats["week"],
        month=db_stats["month"],
        gifts=db_stats["gifts"],
        rw_total=rw.get("total", "—"),
        rw_active=rw.get("active", "—"),
    )


@router.callback_query(F.data == "adm:stats")
async def cb_stats(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    db_stats = await rt.db.sales_stats()
    try:
        rw = await rt.remna.users_count()
    except RemnaError as e:
        rw = {"total": f"ошибка: {e}", "active": "—"}
    await query.message.edit_text(_fmt_stats(rt, db_stats, rw), reply_markup=admin_back())
    await query.answer()


@router.callback_query(F.data == "adm:nodes")
async def cb_nodes(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    try:
        nodes = await rt.remna.list_nodes()
    except RemnaError as e:
        await query.message.edit_text(f"❌ Ошибка: {e}", reply_markup=admin_back())
        await query.answer()
        return
    lines = []
    online = 0
    for n in nodes:
        connected = bool(n.get("isConnected") or n.get("is_connected"))
        online += connected
        lines.append((texts.ADMIN_NODES_ONLINE if connected else texts.ADMIN_NODES_OFFLINE)
                     .format(name=n.get("name", "?")))
    body = "\n".join(lines) if lines else texts.ADMIN_NODES_EMPTY
    await query.message.edit_text(
        texts.ADMIN_NODES.format(nodes=body, total=len(nodes), online=online),
        reply_markup=admin_back(),
    )
    await query.answer()


@router.callback_query(F.data == "adm:check")
async def cb_check_panel(query: CallbackQuery, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await query.answer("Проверяю…")
    results: list[str] = []

    def ok(label, value="OK"):
        results.append(texts.CHECK_OK.format(label=label, value=value))

    def fail(label, error):
        results.append(texts.CHECK_FAIL.format(label=label, error=error))

    try:
        nodes = await rt.remna.list_nodes()
        online = sum(1 for n in nodes if n.get("isConnected"))
        ok("Панель и токен", f"доступна, нод: {len(nodes)}, онлайн: {online}")
    except RemnaError as e:
        fail("Панель и токен", str(e))

    try:
        squads = await rt.remna.list_internal_squads()
        names = ", ".join(f"{s.get('name')} ({s.get('uuid')[:8]}…)" for s in squads[:5]) or "нет"
        configured = rt.cfg.squad_uuid
        extra = ""
        if not configured and squads:
            extra = " — используется первый (задайте REMNAWAVE_SQUAD_UUID)"
        ok("Internal Squads", f"{names}{extra}")
        if configured and not any(s.get("uuid") == configured for s in squads):
            fail("REMNAWAVE_SQUAD_UUID", "squad с таким UUID не найден в панели")
    except RemnaError as e:
        fail("Internal Squads", str(e))

    ok("SUB_PAGE_DOMAIN", rt.cfg.sub_page_domain or "не задан (берём ссылку из панели)")
    ok("Способы оплаты", ", ".join(
        name for name, enabled in {
            "stars": rt.cfg.stars_enabled,
            "cryptobot": rt.cryptobot is not None and rt.cfg.cryptobot_enabled,
            "yookassa": rt.yookassa is not None and rt.cfg.yookassa_enabled,
        }.items() if enabled
    ) or "не настроены")

    if rt.cryptobot:
        try:
            await rt.cryptobot.health()
            ok("CryptoBot API", "токен рабочий")
        except ProviderError as e:
            fail("CryptoBot API", str(e))

    await query.message.edit_text(
        texts.ADMIN_CHECK.format(checks="\n".join(results)), reply_markup=admin_back()
    )


# ─────────────────────────── рассылка ───────────────────────────


@router.callback_query(F.data == "adm:bcast")
async def cb_broadcast(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.set_state(AdminStates.broadcast_message)
    await query.message.edit_text(texts.ADMIN_BROADCAST_ASK)
    await query.answer()


@router.message(AdminStates.broadcast_message)
async def broadcast_preview(message: Message, state: FSMContext, rt: Runtime):
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    users = await rt.db.all_bot_users()
    await message.answer(
        texts.ADMIN_BROADCAST_PREVIEW.format(count=len(users)),
        reply_markup=admin_confirm_broadcast(),
    )


@router.callback_query(F.data == "adm:bcast:go")
async def broadcast_go(query: CallbackQuery, state: FSMContext, rt: Runtime, bot: Bot):
    if not _is_admin(rt, query.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    if not data.get("chat_id"):
        await query.answer("Сначала пришлите сообщение", show_alert=True)
        return
    await query.answer("Отправляю…")
    users = await rt.db.all_bot_users()
    sent = failed = 0
    for tg_id in users:
        try:
            await bot.copy_message(tg_id, data["chat_id"], data["message_id"])
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # ~20 сообщений/сек
    await query.message.edit_text(
        texts.ADMIN_BROADCAST_DONE.format(ok=sent, fail=failed), reply_markup=admin_menu()
    )


# ──────────────────────── выдача подписки ────────────────────────


async def _resolve_target(rt: Runtime, target: str) -> dict | None:
    target = target.strip().lstrip("@")
    if target.isdigit():
        user = await rt.remna.get_user_by_telegram_id(int(target))
        if user:
            return user
    return await rt.remna.get_user_by_username(target)


@router.callback_query(F.data == "adm:grant")
async def cb_grant(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if not _is_admin(rt, query.from_user.id):
        return
    await state.set_state(AdminStates.grant_target)
    await query.message.edit_text(texts.ADMIN_GRANT_ASK_TARGET, reply_markup=admin_back())
    await query.answer()


@router.message(AdminStates.grant_target)
async def grant_target(message: Message, state: FSMContext, rt: Runtime):
    target = (message.text or "").strip()
    if not target:
        await message.answer(texts.ADMIN_GRANT_ASK_TARGET)
        return
    found = await _resolve_target(rt, target)
    if found is None and not target.isdigit():
        await message.answer(texts.ADMIN_USER_NOT_FOUND)
        return
    await state.update_data(target=target)
    await state.set_state(AdminStates.grant_days)
    await message.answer(texts.ADMIN_GRANT_ASK_DAYS)


@router.message(AdminStates.grant_days)
async def grant_days(message: Message, state: FSMContext, rt: Runtime, bot: Bot):
    if not (message.text or "").strip().isdigit():
        await message.answer(texts.ADMIN_ASK_NUMBER)
        return
    days = int(message.text.strip())
    data = await state.get_data()
    await state.clear()
    target = data["target"]

    from ..config import Tariff

    tariff = Tariff(id="gift", title=f"Выдача админом ({days} дн.)", days=days, description="")
    tg_id = int(target) if target.isdigit() else None
    rw_user = await _resolve_target(rt, target)
    try:
        result_text, sub_url = await deliver_subscription(
            rt, tg_id, tariff, existing=rw_user
        )
    except RemnaError as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_back())
        return

    await rt.db.add_payment(
        tg_id or 0, "gift", "admin", "0", "-", status="delivered",
        note=f"target={target}",
    )
    await message.answer(
        texts.ADMIN_GRANT_DONE.format(details=result_text),
        reply_markup=admin_back(),
        disable_web_page_preview=True,
    )
    # уведомляем пользователя, если знаем его Telegram ID
    notify_tg = None
    if tg_id is not None:
        notify_tg = tg_id
    elif rw_user and rw_user.get("telegramId"):
        try:
            notify_tg = int(rw_user["telegramId"])
        except (TypeError, ValueError):
            notify_tg = None
    if notify_tg:
        try:
            await bot.send_message(
                notify_tg,
                "🎁 Администратор выдал вам подписку!\n\n" + result_text,
                reply_markup=subscription_kb(sub_url),
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning("notify granted user: %s", e)


# ──────────────────────── включение / отключение ────────────────────────


async def _toggle(query: CallbackQuery, state: FSMContext, rt: Runtime, disable: bool):
    await state.set_state(AdminStates.ban_target)
    await state.update_data(action="disable" if disable else "enable")
    await query.message.edit_text(
        texts.ADMIN_BAN_ASK if disable else texts.ADMIN_UNBAN_ASK, reply_markup=admin_back()
    )
    await query.answer()


@router.callback_query(F.data == "adm:ban")
async def cb_ban(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if _is_admin(rt, query.from_user.id):
        await _toggle(query, state, rt, disable=True)


@router.callback_query(F.data == "adm:unban")
async def cb_unban(query: CallbackQuery, state: FSMContext, rt: Runtime):
    if _is_admin(rt, query.from_user.id):
        await _toggle(query, state, rt, disable=False)


@router.message(AdminStates.ban_target)
async def ban_target(message: Message, state: FSMContext, rt: Runtime, bot: Bot):
    target = (message.text or "").strip()
    data = await state.get_data()
    await state.clear()
    if not target:
        return
    rw_user = await _resolve_target(rt, target)
    if rw_user is None:
        await message.answer(texts.ADMIN_USER_NOT_FOUND, reply_markup=admin_back())
        return
    action = data.get("action", "disable")
    try:
        if action == "disable":
            await rt.remna.disable_user(rw_user["uuid"])
        else:
            await rt.remna.enable_user(rw_user["uuid"])
    except RemnaError as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_back())
        return
    expire = parse_iso(rw_user.get("expireAt"))
    await message.answer(
        f"{texts.ADMIN_DONE}\n\n"
        f"👤 <code>{rw_user.get('username')}</code>"
        f" (TG: {rw_user.get('telegramId') or '—'})\n"
        f"📅 до {fmt_date(expire, rt.cfg.tz)}\n"
        f"Действие: {'отключён' if action == 'disable' else 'включён'}",
        reply_markup=admin_back(),
    )
    # сообщаем пользователю
    if rw_user.get("telegramId"):
        try:
            user_tg = int(rw_user["telegramId"])
            if action == "disable":
                await bot.send_message(
                    user_tg,
                    "⛔️ Ваша подписка была приостановлена администратором.\n"
                    "Если вы считаете это ошибкой — свяжитесь с поддержкой.",
                )
            else:
                await bot.send_message(
                    user_tg,
                    "✅ Ваша подписка снова активна! Приятного пользования.",
                )
        except Exception:
            pass
