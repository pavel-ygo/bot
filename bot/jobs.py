"""Фоновые задачи: платежи, напоминания, ежедневный бэкап БД."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from aiogram import Bot

from . import texts
from .keyboards import payment_nudge_menu
from .payments import ProviderError
from .services import Runtime, check_reminders, complete_payment, sys_log
from .handlers.buy import _check_external
from .texts import NUDGE_USER, SYS_BACKUP, SYS_NODE_DOWN, SYS_NODE_UP
from .utils import parse_iso, utcnow

log = logging.getLogger(__name__)

POLL_INTERVAL = 20          # сек между опросами платежей
REMINDER_INTERVAL = 6 * 3600  # как часто проверять сроки подписок
BACKUP_INTERVAL = 24 * 3600   # раз в сутки
REPORT_INTERVAL = 4 * 3600    # отчёт админу каждые 4 часа
NODE_CHECK_INTERVAL = 300     # проверка нод каждые 5 минут
BACKUP_KEEP = 7               # сколько копий хранить
NUDGE_AFTER_MINUTES = 60      # напомнить о брошенной оплате через час


async def payment_poller(rt: Runtime, bot: Bot) -> None:
    """Периодически проверяет неоплаченные счета CryptoBot / ЮKassa."""
    log.info("Payment poller started")
    while True:
        try:
            pending = await rt.db.pending_payments()
            for payment in pending:
                provider = payment["provider"]
                if provider not in ("cryptobot", "yookassa"):
                    continue
                status = await _check_external(rt, payment)
                if status == "paid":
                    if await rt.db.claim_payment(payment["id"], "paid"):
                        await complete_payment(rt, bot, int(payment["tg_id"]), payment)
                elif status == "canceled":
                    await rt.db.claim_payment(payment["id"], "canceled")
            expired = await rt.db.expire_stale(hours=24)
            if expired:
                log.info("Expired %s stale invoices", expired)

            # напоминания о брошенных оплатах (раз, потом не дублируем)
            stale = await rt.db.stale_pending_payments(minutes=NUDGE_AFTER_MINUTES)
            for payment in stale:
                await rt.db.set_payment_nudge(payment["id"])
                if payment["provider"] != "card":
                    continue
                tariff = rt.cfg.tariffs.get(payment["tariff_id"])
                if tariff is None:
                    continue
                amount = f"{float(payment['amount']):g} ₽"
                try:
                    await bot.send_message(
                        int(payment["tg_id"]),
                        NUDGE_USER.format(title=tariff.title, amount=amount),
                        reply_markup=payment_nudge_menu(payment["id"]),
                    )
                except Exception:
                    continue
        except ProviderError as e:
            log.warning("poller provider error: %s", e)
        except Exception:
            log.exception("payment poller error")
        await asyncio.sleep(POLL_INTERVAL)


async def reminders_loop(rt: Runtime, bot: Bot) -> None:
    """Раз в REMINDER_INTERVAL часов напоминает о скором окончании подписки."""
    await asyncio.sleep(90)  # даём боту спокойно стартовать
    while True:
        try:
            sent, errors = await check_reminders(rt, bot)
            if sent or errors:
                log.info("reminders: sent=%s errors=%s", sent, errors)
        except Exception:
            log.exception("reminders error")
        await asyncio.sleep(REMINDER_INTERVAL)


async def db_backup_loop(rt: Runtime, bot: Bot) -> None:
    """Ежедневная резервная копия SQLite в data/backups/ (хранятся BACKUP_KEEP шт.)."""
    await asyncio.sleep(90)  # даём боту стартовать
    while True:
        try:
            db_path = Path(rt.cfg.db_path)
            backup_dir = db_path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            target = backup_dir / f"{db_path.stem}-{datetime.now():%Y%m%d-%H%M}.db"
            await rt.db._db.execute("VACUUM INTO ?", (str(target),))
            backups = sorted(backup_dir.glob(f"{db_path.stem}-*.db"))
            for old in backups[:-BACKUP_KEEP]:
                old.unlink()
            log.info("DB backup created: %s", target.name)
            await sys_log(
                rt, bot,
                SYS_BACKUP.format(name=target.name, size=target.stat().st_size // 1024),
            )
            if await rt.db.get_setting("alerts_backup", "1") == "1":
                await send_db_backup_to_admins(rt, bot)
        except Exception:
            log.exception("db backup failed")
        await asyncio.sleep(BACKUP_INTERVAL)


async def _send_admins(rt: Runtime, bot: Bot, text: str) -> None:
    for admin_id in rt.cfg.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


def _format_report(rt: Runtime, period_h: int, stats: dict, nodes: list | None) -> str:
    from .texts import (ADMIN_REPORT_NODES_DOWN, ADMIN_REPORT_NODES_OK,
                        ADMIN_REPORT_PERIOD_4H, ADMIN_PERIOD_REPORT)

    if period_h == 4:
        period = ADMIN_REPORT_PERIOD_4H
    else:
        period = f"{period_h} ч"
    if nodes is None:
        nodes_line = ""
    else:
        down = [n for n in nodes if not n.get("isConnected")]
        if down:
            names = "".join(
                f"  🔴 {n.get('name', '?')}\n" for n in down
            )
            nodes_line = ADMIN_REPORT_NODES_DOWN.format(
                down=len(down), count=len(nodes), names=names,
            )
        else:
            nodes_line = ADMIN_REPORT_NODES_OK.format(count=len(nodes)) if nodes else ""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).astimezone(rt.cfg.tz)
    return ADMIN_PERIOD_REPORT.format(
        period=period,
        period_range=f"(до {now:%d.%m %H:%M} МСК)",
        sales=stats["sales"], rub=stats["rub"],
        new_users=stats["new_users"], ref_bonuses=stats["ref_bonuses"],
        nodes_line=nodes_line,
    )


async def node_monitor(rt: Runtime, bot: Bot) -> None:
    """Каждые 5 минут проверяет ноды и шлёт алерты при смене состояния."""
    await asyncio.sleep(120)
    while True:
        try:
            enabled = await rt.db.get_setting("alerts_nodes", "1") == "1"
            if enabled and rt.cfg.admin_ids:
                nodes = await rt.remna.list_nodes()
                for n in nodes:
                    uuid = n.get("uuid") or n.get("name")
                    name = n.get("name", "?")
                    connected = bool(n.get("isConnected"))
                    prev = await rt.db.get_node_state(uuid)
                    prev_state = prev["state"] if prev else None
                    if not connected and prev_state != "down":
                        await rt.db.set_node_state(uuid, name, "down")
                        await _send_admins(rt, bot, texts.NODE_DOWN_ALERT.format(
                            name=name, since="только что",
                        ))
                        await sys_log(rt, bot, SYS_NODE_DOWN.format(name=name))
                    elif connected and prev_state == "down":
                        minutes = "?"
                        if prev and prev.get("since"):
                            since = parse_iso(prev["since"])
                            if since:
                                minutes = max(1, int((utcnow() - since).total_seconds() // 60))
                        await rt.db.set_node_state(uuid, name, "ok")
                        await _send_admins(rt, bot, texts.NODE_UP_ALERT.format(
                            name=name, minutes=minutes,
                        ))
                        await sys_log(rt, bot, SYS_NODE_UP.format(name=name))
                    elif connected and prev_state is None:
                        await rt.db.set_node_state(uuid, name, "ok")
        except Exception:
            log.exception("node monitor error")
        await asyncio.sleep(NODE_CHECK_INTERVAL)


async def periodic_report(rt: Runtime, bot: Bot) -> None:
    """Каждые 4 часа шлёт админам сводку: продажи, юзеры, ноды."""
    await asyncio.sleep(300)
    while True:
        try:
            enabled = await rt.db.get_setting("reports_enabled", "1") == "1"
            if enabled and rt.cfg.admin_ids:
                stats = await rt.db.period_report(4)
                nodes = None
                try:
                    nodes = await rt.remna.list_nodes()
                except Exception:
                    pass
                report_text = _format_report(rt, 4, stats, nodes)
                await _send_admins(rt, bot, report_text)
                await sys_log(rt, bot, texts.SYS_REPORT.format(period="4 часа"))
        except Exception:
            log.exception("periodic report error")
        await asyncio.sleep(REPORT_INTERVAL)


async def send_db_backup_to_admins(rt: Runtime, bot: Bot) -> None:
    """Отправляет копию БД админам файлом (после создания бэкапа)."""
    from pathlib import Path

    from aiogram.types import BufferedInputFile

    db_path = Path(rt.cfg.db_path)
    backups = sorted((db_path.parent / "backups").glob(f"{db_path.stem}-*.db"))
    if not backups:
        return
    fresh = backups[-1]
    data = fresh.read_bytes()
    for admin_id in rt.cfg.admin_ids:
        try:
            await bot.send_document(
                admin_id,
                BufferedInputFile(data, filename=fresh.name),
                caption=f"💾 Ежедневный бэкап БД ({len(data) // 1024} КБ)",
            )
        except Exception:
            pass
