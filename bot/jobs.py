"""Фоновые задачи: платежи, напоминания, ежедневный бэкап БД."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from aiogram import Bot

from .payments import ProviderError
from .services import Runtime, check_reminders, complete_payment
from .handlers.buy import _check_external

log = logging.getLogger(__name__)

POLL_INTERVAL = 20          # сек между опросами платежей
REMINDER_INTERVAL = 6 * 3600  # как часто проверять сроки подписок
BACKUP_INTERVAL = 24 * 3600   # раз в сутки
BACKUP_KEEP = 7               # сколько копий хранить


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


async def db_backup_loop(rt: Runtime) -> None:
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
        except Exception:
            log.exception("db backup failed")
        await asyncio.sleep(BACKUP_INTERVAL)
