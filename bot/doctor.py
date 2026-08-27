"""Проверка окружения и связи с Remnawave без запуска бота:  python -m bot.doctor"""
from __future__ import annotations

import asyncio
import sys

import httpx

from .config import ConfigError, load_config
from .payments import CryptoBotProvider, ProviderError
from .remnawave import RemnaError, RemnawaveClient

OK, FAIL, WARN = "✅", "❌", "⚠️ "


async def _check_telegram(token: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(f"https://api.telegram.org/bot{token}/getMe")
    except httpx.HTTPError as e:
        return f"{WARN} Telegram: нет сети до api.telegram.org ({e.__class__.__name__})"
    data = resp.json()
    if not data.get("ok"):
        return f"{FAIL} Telegram: токен отклонён ({data.get('description')})"
    me = data["result"]
    return f"{OK} Telegram: бот @{me.get('username')} отвечает"


async def main() -> int:
    print("── Проверка конфигурации ─────────────────────────")
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"{FAIL} Конфигурация: {e}")
        return 1
    print(f"{OK} Конфигурация: {len(cfg.tariffs)} тариф(ов), админов: {len(cfg.admin_ids) or '0 ⚠️'}")
    if not cfg.admin_ids:
        print(f"{WARN} ADMIN_IDS пуст — админ-раздел будет недоступен")

    print("── Telegram ──────────────────────────────────────")
    print(await _check_telegram(cfg.bot_token))

    print("── Remnawave ─────────────────────────────────────")
    rc = RemnawaveClient(cfg)
    code = 0
    try:
        nodes = await rc.list_nodes()
        online = sum(1 for n in nodes if n.get("isConnected"))
        print(f"{OK} Панель: доступна, токен рабочий")
        print(f"   Ноды ({len(nodes)}): "
              + ", ".join(
                  f"{n.get('name')} [{'online' if n.get('isConnected') else 'OFFLINE'}]"
                  for n in nodes) or "нет нод")
        if not nodes:
            print(f"{WARN} Ноды не найдены — проверьте панель")
        elif online == 0:
            print(f"{WARN} Ни одна нода не подключена!")
        squads = await rc.list_internal_squads()
        if not squads:
            print(f"{FAIL} Internal Squads: не найдены. Создайте squad в панели и добавьте хосты.")
            code = 1
        else:
            print(f"{OK} Internal Squads: " + ", ".join(
                f"{s.get('name')} ({s.get('uuid')})" for s in squads))
            if cfg.squad_uuid and not any(s.get("uuid") == cfg.squad_uuid for s in squads):
                print(f"{FAIL} REMNAWAVE_SQUAD_UUID не найден среди squads панели!")
                code = 1
            elif not cfg.squad_uuid:
                print(f"{WARN} REMNAWAVE_SQUAD_UUID не задан — будет использован первый squad")
        stats = await rc.users_count()
        print(f"   Пользователей в панели: {stats['total']} (активных: {stats['active']})")
        print(f"{OK} SUB_PAGE_DOMAIN: {cfg.sub_page_domain or 'не задан — ссылки берутся из панели'}")
    except RemnaError as e:
        print(f"{FAIL} Панель: {e}")
        print("   Проверьте REMNAWAVE_PANEL_URL и REMNAWAVE_API_TOKEN")
        code = 1
    finally:
        await rc.aclose()

    if cfg.cryptobot_enabled:
        cb = CryptoBotProvider(cfg.cryptobot_token, testnet=cfg.cryptobot_testnet)
        try:
            await cb.health()
            print(f"{OK} CryptoBot: токен рабочий"
                  + (" (testnet)" if cfg.cryptobot_testnet else ""))
        except ProviderError as e:
            print(f"{FAIL} CryptoBot: {e}")
            code = 1
        finally:
            await cb.aclose()
    elif cfg.cryptobot_token:
        print(f"{WARN} CryptoBot: токен задан, но ни у одного тарифа нет price_usdt")
    if cfg.yookassa_shop_id and not cfg.yookassa_enabled:
        print(f"{WARN} ЮKassa: реквизиты заданы не полностью или нет price_rub у тарифов")

    print("──────────────────────────────────────────────────")
    print("Всё готово к запуску: python -m bot" if code == 0
          else "Исправьте ошибки выше и повторите: python -m bot.doctor")
    return code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
