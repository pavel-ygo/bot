"""Точка входа: сборка и запуск бота."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage

from .config import ConfigError, load_config
from .db import Database
from .handlers import admin, admin_extra, bonus, buy, pay_card, support, user
from .jobs import (db_backup_loop, node_monitor, payment_poller,
                   periodic_report, reminders_loop)
from .payments import CryptoBotProvider, YooKassaProvider
from .remnawave import RemnawaveClient
from .services import Runtime


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        cfg = load_config()
    except ConfigError as e:
        raise SystemExit(f"❌ Ошибка конфигурации:\n{e}")

    db = await Database.create(cfg.db_path)
    remna = RemnawaveClient(cfg)
    rt = Runtime(cfg=cfg, db=db, remna=remna)
    if cfg.cryptobot_enabled:
        rt.cryptobot = CryptoBotProvider(cfg.cryptobot_token, testnet=cfg.cryptobot_testnet)
    if cfg.yookassa_enabled:
        rt.yookassa = YooKassaProvider(cfg.yookassa_shop_id, cfg.yookassa_secret)

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError:
        raise SystemExit(
            "❌ Telegram отклонил BOT_TOKEN — токен неверный или отозван.\n"
            "   Откройте файл .env в корне проекта (рядом с docker-compose.yml),\n"
            "   исправьте строку BOT_TOKEN=... и пересоздайте контейнер:\n"
            "   docker compose up -d\n"
            "   Токен вида 123456789:AA... выдаёт @BotFather (/mybots → API Token).\n"
            "   Проверить токен вручную: curl -s https://api.telegram.org/bot<ТОКЕН>/getMe"
        )
    rt.bot_username = me.username

    dp = Dispatcher(storage=MemoryStorage())
    dp["rt"] = rt

    dp.include_router(user.router)
    dp.include_router(buy.router)
    dp.include_router(pay_card.router)
    dp.include_router(bonus.router)
    dp.include_router(admin.router)
    dp.include_router(admin_extra.router)
    dp.include_router(support.router)

    logging.info("Запуск бота @%s | тарифов: %s | админов: %s",
                 me.username, len(cfg.tariffs), len(cfg.admin_ids))
    await bot.delete_webhook(drop_pending_updates=True)

    tasks = [
        asyncio.create_task(payment_poller(rt, bot), name="payment-poller"),
        asyncio.create_task(reminders_loop(rt, bot), name="reminders"),
        asyncio.create_task(db_backup_loop(rt, bot), name="db-backup"),
        asyncio.create_task(node_monitor(rt, bot), name="node-monitor"),
        asyncio.create_task(periodic_report(rt, bot), name="periodic-report"),
    ]
    try:
        await dp.start_polling(bot)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await remna.aclose()
        if rt.cryptobot:
            await rt.cryptobot.aclose()
        if rt.yookassa:
            await rt.yookassa.aclose()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code:
            print(e.code)
