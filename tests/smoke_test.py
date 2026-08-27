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


async def main():
    await test_utils()
    await test_db()
    await test_create_path()
    await test_extend_path()
    await test_client_unwrap()
    print(f"\n✅ Все тесты пройдены: {PASSED} проверок")


if __name__ == "__main__":
    asyncio.run(main())
