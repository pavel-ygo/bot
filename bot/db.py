"""SQLite-хранилище бота (aiosqlite): пользователи бота, платежи, напоминания."""
from __future__ import annotations

from datetime import timedelta

import aiosqlite

from .utils import utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS bot_users (
    tg_id         INTEGER PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    created_at    TEXT NOT NULL,
    last_seen     TEXT,
    last_reminder TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id        INTEGER NOT NULL,
    tariff_id    TEXT    NOT NULL,
    provider     TEXT    NOT NULL,            -- stars | cryptobot | yookassa | admin
    ext_id       TEXT,                         -- id счёта у провайдера
    amount       TEXT    NOT NULL,
    currency     TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'pending',  -- pending|paid|delivered|canceled|error
    created_at   TEXT    NOT NULL,
    paid_at      TEXT,
    delivered_at TEXT,
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_payments_status  ON payments (status);
CREATE INDEX IF NOT EXISTS idx_payments_tg      ON payments (tg_id);
CREATE INDEX IF NOT EXISTS idx_payments_ext     ON payments (provider, ext_id);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._db: aiosqlite.Connection | None = None

    @classmethod
    async def create(cls, path: str) -> "Database":
        import pathlib

        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self = cls(path)
        self._db = await aiosqlite.connect(path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        return self

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ── пользователи бота ──────────────────────────────────────────────

    async def upsert_bot_user(self, tg_id: int, username: str | None, first_name: str | None) -> None:
        now = utcnow().isoformat()
        await self._db.execute(
            """
            INSERT INTO bot_users (tg_id, username, first_name, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (tg_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = excluded.last_seen
            """,
            (tg_id, username, first_name, now, now),
        )
        await self._db.commit()

    async def all_bot_users(self) -> list[int]:
        async with self._db.execute("SELECT tg_id FROM bot_users") as cur:
            return [row[0] for row in await cur.fetchall()]

    async def get_reminder(self, tg_id: int) -> str | None:
        async with self._db.execute(
            "SELECT last_reminder FROM bot_users WHERE tg_id = ?", (tg_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

    async def set_reminder(self, tg_id: int, code: str) -> None:
        await self._db.execute(
            "UPDATE bot_users SET last_reminder = ? WHERE tg_id = ?", (code, tg_id)
        )
        await self._db.commit()

    # ── платежи ────────────────────────────────────────────────────────

    async def add_payment(
        self, tg_id: int, tariff_id: str, provider: str,
        amount: str, currency: str, ext_id: str | None = None,
        status: str = "pending", note: str | None = None,
    ) -> int:
        cur = await self._db.execute(
            """
            INSERT INTO payments (tg_id, tariff_id, provider, ext_id, amount, currency,
                                  status, created_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tg_id, tariff_id, provider, ext_id, amount, currency, status,
             utcnow().isoformat(), note),
        )
        await self._db.commit()
        return cur.lastrowid

    async def get_payment(self, payment_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM payments WHERE id = ?", (payment_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def claim_payment(self, payment_id: int, new_status: str) -> bool:
        """Атомарно переводит pending -> new_status. True, если успели первыми (идемпотентность)."""
        cur = await self._db.execute(
            "UPDATE payments SET status = ?, paid_at = ? WHERE id = ? AND status = 'pending'",
            (new_status, utcnow().isoformat(), payment_id),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def mark_delivered(self, payment_id: int) -> None:
        await self._db.execute(
            "UPDATE payments SET status = 'delivered', delivered_at = ? "
            "WHERE id = ? AND status IN ('paid','pending')",
            (utcnow().isoformat(), payment_id),
        )
        await self._db.commit()

    async def mark_error(self, payment_id: int, note: str) -> None:
        await self._db.execute(
            "UPDATE payments SET status = 'error', note = ? WHERE id = ?", (note[:500], payment_id)
        )
        await self._db.commit()

    async def pending_payments(self, provider: str | None = None) -> list[dict]:
        query = "SELECT * FROM payments WHERE status = 'pending'"
        params: tuple = ()
        if provider:
            query += " AND provider = ?"
            params = (provider,)
        async with self._db.execute(query, params) as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def expire_stale(self, hours: int = 24) -> int:
        cutoff = (utcnow() - timedelta(hours=hours)).isoformat()
        cur = await self._db.execute(
            "UPDATE payments SET status = 'canceled' WHERE status = 'pending' AND created_at < ?",
            (cutoff,),
        )
        await self._db.commit()
        return cur.rowcount or 0

    # ── статистика ─────────────────────────────────────────────────────

    async def sales_stats(self) -> dict:
        """Сводка по оплаченным продажам (status IN paid/delivered)."""
        async with self._db.execute(
            """
            SELECT provider, currency, COUNT(*) AS cnt, SUM(CAST(amount AS REAL)) AS total
            FROM payments
            WHERE status IN ('paid','delivered') AND provider != 'admin'
            GROUP BY provider, currency
            """
        ) as cur:
            by_provider = [dict(r) for r in await cur.fetchall()]

        async with self._db.execute(
            "SELECT COUNT(*) FROM payments WHERE status = 'delivered' AND provider = 'admin'"
        ) as cur:
            gifts = (await cur.fetchone())[0]

        async with self._db.execute(
            """
            SELECT COUNT(*) FROM payments
            WHERE status IN ('paid','delivered') AND provider != 'admin'
              AND created_at >= datetime('now', '-7 days')
            """
        ) as cur:
            week = (await cur.fetchone())[0]

        async with self._db.execute(
            """
            SELECT COUNT(*) FROM payments
            WHERE status IN ('paid','delivered') AND provider != 'admin'
              AND created_at >= datetime('now', '-30 days')
            """
        ) as cur:
            month = (await cur.fetchone())[0]

        async with self._db.execute("SELECT COUNT(*) FROM bot_users") as cur:
            bot_users = (await cur.fetchone())[0]

        return {
            "by_provider": by_provider,
            "gifts": gifts,
            "week": week,
            "month": month,
            "bot_users": bot_users,
        }
