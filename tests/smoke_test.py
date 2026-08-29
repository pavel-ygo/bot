"""Смоук-тесты: бизнес-логика бота против эмулируемого API Remnawave.

Запуск:  python -m tests.smoke_test
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.update(
    BOT_TOKEN="123456789:AAfakeTokenForTests_fakeTokenForTests",
    ADMIN_IDS="111",
    REMNAWAVE_PANEL_URL="https://panel.test",
    REMNAWAVE_API_TOKEN="fake-token",
    REMNAWAVE_SQUAD_UUID="squad-uuid-1",
    SUB_PAGE_DOMAIN="https://sub.test",
    TARIFFS=json.dumps({"m1": {"title": "1 месяц", "days": 30, "price_rub": 199,
                               "price_stars": 150, "price_usdt": 1.99}}),
    DB_PATH="/tmp/test_bot.db",
)

from bot.config import load_config  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.remnawave import RemnaError, RemnawaveClient  # noqa: E402
from bot.services import Runtime, deliver_subscription  # noqa: E402
from bot.config import Tariff  # noqa: E402
from bot.utils import fmt_bytes, human_days_left, parse_iso, to_iso  # noqa: E402

import httpx  # noqa: E402

PASSED = 0


def check(name: str, cond: bool, extra: str = ""):
    global PASSED
    assert cond, f"FAIL: {name} {extra}"
    PASSED += 1
    print(f"  ✓ {name}")


class FakeRemna:
    """Эмуляция панели: перехватываем http-слой RemnawaveClient."""

    def __init__(self, existing_user: dict | None):
        self.calls: list[tuple[str, str]] = []
        self.existing = existing_user
        self.created: dict | None = None
        self.patches: list[dict] = []
        self.client = httpx.AsyncClient(
            base_url="https://panel.test",
            transport=httpx.MockTransport(self._handler),
        )

    async def _handler(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        self.calls.append((method, path))
        api = path.removeprefix("/api")

        if api == "/internal-squads" and method == "GET":
            return httpx.Response(200, json={"response": [
                {"uuid": "squad-uuid-1", "name": "Main squad"}]})

        if api.startswith("/users/by-telegram-id/") and method == "GET":
            if self.existing:
                return httpx.Response(200, json={"response": [self.existing]})
            return httpx.Response(200, json={"response": []})

        if api == "/users" and method == "POST":
            body = json.loads(request.content)
            self.created = {"uuid": "uuid-new", "shortUuid": "abc123",
                            "username": body["username"], "status": "ACTIVE",
                            "expireAt": body["expireAt"],
                            "subscriptionUrl": "https://sub.test/abc123",
                            **body}
            return httpx.Response(200, json={"response": self.created})

        if api == "/users" and method == "PATCH":
            body = json.loads(request.content)
            self.patches.append(body)
            return httpx.Response(200, json={"response": {**(self.existing or {}), **body}})

        if api.startswith("/users/") and api.endswith("/actions/enable"):
            return httpx.Response(200, json={"response": {"status": "ACTIVE"}})

        if api.startswith("/users/") and api.endswith("/actions/reset-traffic"):
            return httpx.Response(200, json={"response": {}})

        if api.startswith("/users/") and method == "GET":
            source = self.created or self.existing or {}
            return httpx.Response(200, json={"response": source})

        return httpx.Response(404, json={"message": f"unknown {method} {path}"})

    async def aclose(self):
        await self.client.aclose()


def make_rt(fake: FakeRemna) -> Runtime:
    cfg = load_config()
    db = Database("/tmp/test_bot.db")  # не открываем: БД не нужна в этих тестах
    rt = Runtime(cfg=cfg, db=db, remna=RemnawaveClient(cfg))
    rt.remna._http = fake.client  # подменяем транспорт эмуляцией
    rt._squad_uuid = "squad-uuid-1"
    return rt


TARIFF = Tariff(id="m1", title="1 месяц", days=30, description="",
                price_rub=199, price_stars=150, price_usdt=1.99)


async def test_utils():
    print("utils:")
    dt = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    check("to_iso", to_iso(dt) == "2025-06-01T12:00:00.000Z")
    check("parse_iso", parse_iso("2025-06-01T12:00:00.000Z") == dt)
    check("parse_iso +00:00", parse_iso("2025-06-01T12:00:00+00:00") == dt)
    check("fmt_bytes", fmt_bytes(1536) == "1.50 КБ" and fmt_bytes(3 * 1024 ** 3).endswith("ГБ"))
    future = datetime.now(timezone.utc) + timedelta(days=2, hours=5)
    check("days_left", human_days_left(future) == 3)


async def test_db():
    print("db:")
    db = await Database.create("/tmp/test_bot.db")
    pid = await db.add_payment(1, "m1", "cryptobot", "1.99", "USDT", ext_id="42")
    check("add_payment", pid > 0)
    check("claim once", await db.claim_payment(pid, "paid"))
    check("claim twice -> False", not await db.claim_payment(pid, "paid"))
    p = await db.get_payment(pid)
    check("status=paid", p["status"] == "paid")
    await db.mark_delivered(pid)
    check("delivered", (await db.get_payment(pid))["status"] == "delivered")
    stats = await db.sales_stats()
    check("stats", stats["by_provider"][0]["cnt"] == 1)
    await db._db.execute("DELETE FROM payments")
    await db._db.commit()
    await db.close()


async def test_settings_and_promo():
    print("db: настройки, промокоды, кампании, trial:")
    db = await Database.create("/tmp/test_bot2.db")
    try:
        # настройки
        check("setting default", await db.get_setting("pay_stars", "1") == "1")
        await db.set_setting("pay_stars", "0")
        check("setting set", await db.get_setting("pay_stars", "1") == "0")

        # источник (рекламная кампания)
        await db.upsert_bot_user(500, "u5", "U5", source="tg-ads")
        await db.upsert_bot_user(500, "u5", "U5")  # повторный вход не меняет источник
        cur = await db._db.execute("SELECT source FROM bot_users WHERE tg_id=500")
        r = await cur.fetchone()
        check("source fixed on first start", r[0] == "tg-ads")
        await db.add_payment(500, "m1", "stars", "150", "XTR", status="delivered")
        st = await db.campaign_stats()
        check("campaign stats", st["tg-ads"]["users"] == 1 and st["tg-ads"]["paid"] == 1)
    finally:
        await db.close()


async def test_promo_rules():
    print("db: правила промокодов и trial:")
    from datetime import timedelta

    from bot.utils import utcnow

    db = await Database.create("/tmp/test_bot3.db")
    try:
        check("promo create", await db.create_promo("WELCOME", 1, max_uses=2))
        check("promo duplicate -> False", not await db.create_promo("WELCOME", 5))
        promo, reason = await db.activate_promo("welcome", 777)  # регистронезависимо
        check("promo activate", promo is not None and promo["days"] == 1)
        promo2, reason2 = await db.activate_promo("WELCOME", 777)
        check("promo per-user once", promo2 is None and reason2 == "already")
        promo3, _ = await db.activate_promo("WELCOME", 778)
        check("promo second user ok", promo3 is not None)
        promo4, reason4 = await db.activate_promo("WELCOME", 779)
        check("promo limit reached", promo4 is None and reason4 == "limit")
        check("promo used counter", (await db.list_promos())[0]["used"] == 2)
        await db.set_promo_active((await db.list_promos())[0]["id"], False)
        promo5, _ = await db.activate_promo("WELCOME", 780)
        check("promo disabled", promo5 is None)
        await db.delete_promo((await db.list_promos())[0]["id"])
        check("promo deleted", await db.list_promos() == [])

        await db.create_promo("OLD", 3, expires_at=(utcnow() - timedelta(days=1)).isoformat())
        promo6, reason6 = await db.activate_promo("OLD", 781)
        check("promo expired", promo6 is None and reason6 == "expired")

        await db.upsert_bot_user(500, "u5", "U5")
        check("trial not used", not await db.trial_used(500))
        await db.mark_trial_used(500)
        check("trial used", await db.trial_used(500))
        check("trials count", await db.trials_count() == 1)
    finally:
        await db.close()


async def test_create_path():
    print("выдача: новый пользователь:")
    fake = FakeRemna(existing_user=None)
    rt = make_rt(fake)
    text, url = await deliver_subscription(rt, 424242, TARIFF)
    check("текст содержит ссылку", "https://sub.test/abc123" in text)
    check("ссылка возвращена", url == "https://sub.test/abc123")
    check("юзер создан с tg id", fake.created and fake.created["username"].startswith("tg424242"))
    check("telegramId записан", fake.created.get("telegramId") == 424242)
    check("squad назначен", fake.created.get("activeInternalSquads") == ["squad-uuid-1"])
    expire = parse_iso(fake.created["expireAt"])
    days = (expire - datetime.now(timezone.utc)).total_seconds() / 86400
    check("срок = 30 дней", 29.9 < days < 30.1, f"({days})")
    await fake.aclose()


async def test_extend_path():
    print("выдача: продление существующего:")
    future = datetime.now(timezone.utc) + timedelta(days=10)
    existing = {"uuid": "uuid-old", "shortUuid": "old123", "username": "tg100",
                "status": "ACTIVE", "expireAt": to_iso(future)}
    fake = FakeRemna(existing_user=existing)
    rt = make_rt(fake)
    text, url = await deliver_subscription(rt, 100, TARIFF)
    check("текст про продление", "продлена" in text)
    patch = next(p for p in fake.patches if "expireAt" in p)
    new_expire = parse_iso(patch["expireAt"])
    days = (new_expire - future).total_seconds() / 86400
    check("продление = старый срок + 30д", 29.9 < days < 30.1, f"({days})")

    # истёкший пользователь: база = сейчас
    past = datetime.now(timezone.utc) - timedelta(days=5)
    fake2 = FakeRemna(existing_user={**existing, "expireAt": to_iso(past)})
    rt2 = make_rt(fake2)
    await deliver_subscription(rt2, 100, TARIFF)
    patch2 = next(p for p in fake2.patches if "expireAt" in p)
    days2 = (parse_iso(patch2["expireAt"]) - datetime.now(timezone.utc)).total_seconds() / 86400
    check("истёкший: +30д от сейчас", 29.9 < days2 < 30.1, f"({days2})")
    await fake.aclose()
    await fake2.aclose()


async def test_client_unwrap():
    print("remnawave client:")
    cfg = load_config()
    client = RemnawaveClient(cfg)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/nodes":
            return httpx.Response(200, json={"response": [{"name": "node-1", "isConnected": True}]})
        if request.url.path == "/api/users":
            return httpx.Response(200, json={"response": {"users": [], "total": 777}})
        return httpx.Response(500)

    client._http = httpx.AsyncClient(base_url="https://panel.test",
                                     transport=httpx.MockTransport(handler))
    nodes = await client.list_nodes()
    check("unwrap nodes", nodes[0]["name"] == "node-1")
    counts = await client.users_count()
    check("users total", counts["total"] == 777)
    try:
        client2 = RemnawaveClient(cfg)
        client2._http = httpx.AsyncClient(
            base_url="https://panel.test",
            transport=httpx.MockTransport(
                lambda r: httpx.Response(404, json={"message": "not found"})),
        )
        await client2._request("GET", "/users/xxx")
        check("404 raises", False)
    except RemnaError as e:
        check("404 raises", e.status == 404)
    await client._http.aclose()
    await client2._http.aclose()
    await client.aclose()
    await client2.aclose()


async def test_tickets_and_refs():
    print("db: тикеты поддержки и рефералы:")
    db = await Database.create("/tmp/test_bot4.db")
    try:
        # тикеты
        tid = await db.create_ticket(900)
        check("ticket created", tid > 0)
        t = await db.get_ticket(tid)
        check("ticket open by default", t["status"] == "open")
        check("open ticket for user", (await db.open_ticket_for_user(900))["id"] == tid)
        await db.add_ticket_message(tid, "user", 900, 900, 42)
        await db.set_ticket_status(tid, "answered")
        check("ticket answered", (await db.get_ticket(tid))["status"] == "answered")
        check("still in open list", len(await db.open_tickets()) == 1)
        await db.set_ticket_status(tid, "closed")
        check("closed removed from list", await db.open_tickets() == [])
        check("no open ticket now", await db.open_ticket_for_user(900) is None)

        # рефералы
        await db.upsert_bot_user(1000, "ref", "Ref")
        await db.upsert_bot_user(1001, "refd", "Refd", referred_by="1000")
        check("created flag works", True)
        check("referrals count", await db.count_referrals(1000) == 1)
        check("no paid referrals yet", await db.paid_referrals(1000) == 0)
        await db.add_payment(1001, "m1", "stars", "150", "XTR", status="delivered")
        check("paid referral counted", await db.paid_referrals(1000) == 1)
        check("delivered_paid_count", await db.delivered_paid_count(1001) == 1)
        await db.add_payment(1000, "refbonus", "refbonus", "3", "days", status="delivered")
        check("bonus days total", await db.ref_bonus_days_total(1000) == 3)
        check("referrals_total", await db.referrals_total() == 1)

        # upsert не перетирает source/referred_by
        created2 = await db.upsert_bot_user(1001, "refd2", "Refd")
        check("second upsert -> False", created2 is False)
        bu = await db.get_bot_user(1001)
        check("referred_by preserved", bu["referred_by"] == "1000")
    finally:
        await db.close()


async def test_card_provider():
    print("оплата: способы и дефолты (карта вкл, stars/крипта выкл):")
    from bot.config import Tariff
    from bot.services import Runtime, card_settings

    db = await Database.create("/tmp/test_bot5.db")
    try:
        cfg = load_config()
        rt = Runtime(cfg=cfg, db=db, remna=None)
        tariff = cfg.tariffs["m1"]

        # без реквизитов карты способ недоступен
        providers = await rt.available_providers(tariff)
        check("card off without credentials", providers["card"] is False)
        check("stars default off", providers["stars"] is False)
        check("cryptobot default off", providers["cryptobot"] is False)
        check("yookassa default off", providers["yookassa"] is False)

        # задали реквизиты -> карта доступна
        await rt.db.set_setting("card_number", "2202 2037 1234 5678")
        await rt.db.set_setting("card_bank", "Т-Банк")
        providers = await rt.available_providers(tariff)
        check("card on with credentials", providers["card"] is True)
        cs = await card_settings(rt)
        check("card settings stored", cs["number"].endswith("5678") and cs["bank"] == "Т-Банк")

        # выключили тумблером
        await rt.db.set_setting("pay_card", "0")
        providers = await rt.available_providers(tariff)
        check("card toggle off", providers["card"] is False)

        # stars включается админом
        await rt.db.set_setting("pay_stars", "1")
        providers = await rt.available_providers(tariff)
        check("stars re-enabled", providers["stars"] is True)
    finally:
        await db.close()


async def main():
    await test_utils()
    await test_db()
    await test_settings_and_promo()
    await test_promo_rules()
    await test_tickets_and_refs()
    await test_card_provider()
    await test_create_path()
    await test_extend_path()
    await test_client_unwrap()
    print(f"\n✅ Все тесты пройдены: {PASSED} проверок")


if __name__ == "__main__":
    asyncio.run(main())


