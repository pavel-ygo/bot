"""SQLite-хранилище бота (aiosqlite): пользователи, платежи, промокоды, кампании, настройки."""
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
    last_reminder TEXT,
    source        TEXT,
    trial_used    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id        INTEGER NOT NULL,
    tariff_id    TEXT    NOT NULL,
    provider     TEXT    NOT NULL,            -- stars | cryptobot | yookassa | admin | promo | trial
    ext_id       TEXT,                         -- id счёта у провайдера
    amount       TEXT    NOT NULL,
    currency     TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'pending',  -- pending|paid|delivered|canceled|error
    created_at   TEXT    NOT NULL,
    paid_at      TEXT,
    delivered_at TEXT,
    note         TEXT,
    source       TEXT
);
CREATE INDEX IF NOT EXISTS idx_payments_status  ON payments (status);
CREATE INDEX IF NOT EXISTS idx_payments_tg      ON payments (tg_id);
CREATE INDEX IF NOT EXISTS idx_payments_ext     ON payments (provider, ext_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaigns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS promo_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT UNIQUE NOT NULL,
    days       INTEGER NOT NULL,
    max_uses   INTEGER NOT NULL DEFAULT 0,   -- 0 = безлимит
    used       INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,                          -- ISO UTC или NULL
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS promo_activations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    promo_id   INTEGER NOT NULL,
    tg_id      INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (promo_id, tg_id)
);

CREATE TABLE IF NOT EXISTS tickets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id      INTEGER NOT NULL,
    status     TEXT NOT NULL DEFAULT 'open',  -- open | answered | closed
    created_at TEXT NOT NULL,
    updated_at TEXT,
    closed_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER NOT NULL,
    role       TEXT NOT NULL,                 -- user | admin
    tg_id      INTEGER NOT NULL,
    chat_id    INTEGER,
    message_id INTEGER,
    created_at TEXT NOT NULL
);
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
        await self._migrate()
        await self._db.commit()
        return self

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def _migrate(self) -> None:
        """Мягкие миграции для баз, созданных старыми версиями бота."""

        async def has_col(table: str, col: str) -> bool:
            async with self._db.execute(f"PRAGMA table_info({table})") as cur:
                return any(r[1] == col for r in await cur.fetchall())

        if not await has_col("bot_users", "source"):
            await self._db.execute("ALTER TABLE bot_users ADD COLUMN source TEXT")
        if not await has_col("bot_users", "trial_used"):
            await self._db.execute(
                "ALTER TABLE bot_users ADD COLUMN trial_used INTEGER NOT NULL DEFAULT 0"
            )
        if not await has_col("payments", "source"):
            await self._db.execute("ALTER TABLE payments ADD COLUMN source TEXT")
        if not await has_col("bot_users", "referred_by"):
            await self._db.execute("ALTER TABLE bot_users ADD COLUMN referred_by TEXT")
        if not await has_col("payments", "verified"):
            await self._db.execute(
                "ALTER TABLE payments ADD COLUMN verified INTEGER NOT NULL DEFAULT 0"
            )

    # ── пользователи бота ──────────────────────────────────────────────

    async def upsert_bot_user(
        self, tg_id: int, username: str | None, first_name: str | None,
        source: str | None = None, referred_by: str | None = None,
    ) -> bool:
        """Создаёт/обновляет пользователя. source/referred_by фиксируются только при первом входе.

        Возвращает True, если пользователь создан (первый запуск).
        """
        now = utcnow().isoformat()
        async with self._db.execute(
            "SELECT 1 FROM bot_users WHERE tg_id = ?", (tg_id,)
        ) as cur:
            exists = await cur.fetchone()
        if exists:
            await self._db.execute(
                "UPDATE bot_users SET username = ?, first_name = ?, last_seen = ? WHERE tg_id = ?",
                (username, first_name, now, tg_id),
            )
            await self._db.commit()
            return False
        await self._db.execute(
            """
            INSERT INTO bot_users (tg_id, username, first_name, created_at, last_seen,
                                   source, referred_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tg_id, username, first_name, now, now, source, referred_by),
        )
        await self._db.commit()
        return True

    async def get_bot_user(self, tg_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM bot_users WHERE tg_id = ?", (tg_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def all_bot_users(self) -> list[int]:
        async with self._db.execute("SELECT tg_id FROM bot_users") as cur:
            return [row[0] for row in await cur.fetchall()]

    async def all_bot_users_full(self) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM bot_users ORDER BY tg_id"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def all_payments(self, limit: int = 10000) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM payments ORDER BY id LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

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

    # ── пробный период ─────────────────────────────────────────────────

    async def trial_used(self, tg_id: int) -> bool:
        async with self._db.execute(
            "SELECT trial_used FROM bot_users WHERE tg_id = ?", (tg_id,)
        ) as cur:
            row = await cur.fetchone()
            return bool(row and row[0])

    async def mark_trial_used(self, tg_id: int) -> None:
        await self._db.execute(
            "UPDATE bot_users SET trial_used = 1 WHERE tg_id = ?", (tg_id,)
        )
        await self._db.commit()

    async def trials_count(self) -> int:
        async with self._db.execute(
            "SELECT COUNT(*) FROM bot_users WHERE trial_used = 1"
        ) as cur:
            return (await cur.fetchone())[0]

    # ── настройки (runtime-переключатели) ──────────────────────────────

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        async with self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self._db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        await self._db.commit()

    # ── промокоды ──────────────────────────────────────────────────────

    async def create_promo(
        self, code: str, days: int, max_uses: int = 0, expires_at: str | None = None
    ) -> bool:
        """False, если код уже существует."""
        try:
            await self._db.execute(
                "INSERT INTO promo_codes (code, days, max_uses, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (code, days, max_uses, expires_at, utcnow().isoformat()),
            )
            await self._db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def list_promos(self, limit: int = 15) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM promo_codes ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_promo(self, promo_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM promo_codes WHERE id = ?", (promo_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def set_promo_active(self, promo_id: int, active: bool) -> None:
        await self._db.execute(
            "UPDATE promo_codes SET active = ? WHERE id = ?", (1 if active else 0, promo_id)
        )
        await self._db.commit()

    async def delete_promo(self, promo_id: int) -> None:
        await self._db.execute("DELETE FROM promo_activations WHERE promo_id = ?", (promo_id,))
        await self._db.execute("DELETE FROM promo_codes WHERE id = ?", (promo_id,))
        await self._db.commit()

    async def activate_promo(self, code: str, tg_id: int) -> tuple[dict | None, str | None]:
        """Активирует промокод. Возвращает (промокод, None) или (None, причина)."""
        code = code.strip().upper()
        async with self._db.execute(
            "SELECT * FROM promo_codes WHERE code = ?", (code,)
        ) as cur:
            promo = await cur.fetchone()
        if promo is None or not promo["active"]:
            return None, "not_found"
        if promo["expires_at"] and promo["expires_at"] < utcnow().isoformat():
            return None, "expired"
        if promo["max_uses"] and promo["used"] >= promo["max_uses"]:
            return None, "limit"
        async with self._db.execute(
            "SELECT 1 FROM promo_activations WHERE promo_id = ? AND tg_id = ?",
            (promo["id"], tg_id),
        ) as cur:
            if await cur.fetchone():
                return None, "already"
        await self._db.execute(
            "INSERT INTO promo_activations (promo_id, tg_id, created_at) VALUES (?, ?, ?)",
            (promo["id"], tg_id, utcnow().isoformat()),
        )
        await self._db.execute(
            "UPDATE promo_codes SET used = used + 1 WHERE id = ?", (promo["id"],)
        )
        await self._db.commit()
        return dict(promo), None

    # ── рекламные кампании ─────────────────────────────────────────────

    async def add_campaign(self, name: str) -> bool:
        try:
            await self._db.execute(
                "INSERT INTO campaigns (name, created_at) VALUES (?, ?)",
                (name, utcnow().isoformat()),
            )
            await self._db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def list_campaigns(self) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM campaigns ORDER BY id DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def delete_campaign(self, campaign_id: int) -> None:
        await self._db.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
        await self._db.commit()

    async def campaign_stats(self) -> dict[str, dict]:
        """{name: {users, paid, revenue: {currency: total}}} по всем кампаниям."""
        stats: dict[str, dict] = {}
        async with self._db.execute(
            "SELECT source, COUNT(*) AS c FROM bot_users "
            "WHERE source IS NOT NULL GROUP BY source"
        ) as cur:
            for src, cnt in await cur.fetchall():
                stats.setdefault(src, {"users": 0, "paid": 0, "revenue": {}})
                stats[src]["users"] = cnt
        async with self._db.execute(
            """
            SELECT source, currency, COUNT(*) AS cnt, SUM(CAST(amount AS REAL)) AS total
            FROM payments
            WHERE source IS NOT NULL AND status IN ('paid','delivered')
              AND provider NOT IN ('admin')
            GROUP BY source, currency
            """
        ) as cur:
            for src, cur_code, cnt, total in await cur.fetchall():
                item = stats.setdefault(src, {"users": 0, "paid": 0, "revenue": {}})
                item["paid"] += cnt
                item["revenue"][cur_code] = item["revenue"].get(cur_code, 0) + (total or 0)
        return stats

    # ── платежи ────────────────────────────────────────────────────────

    async def add_payment(
        self, tg_id: int, tariff_id: str, provider: str,
        amount: str, currency: str, ext_id: str | None = None,
        status: str = "pending", note: str | None = None,
    ) -> int:
        source: str | None = None
        if tg_id:
            async with self._db.execute(
                "SELECT source FROM bot_users WHERE tg_id = ?", (tg_id,)
            ) as cur:
                row = await cur.fetchone()
                source = row[0] if row else None
        cur = await self._db.execute(
            """
            INSERT INTO payments (tg_id, tariff_id, provider, ext_id, amount, currency,
                                  status, created_at, note, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tg_id, tariff_id, provider, ext_id, amount, currency, status,
             utcnow().isoformat(), note, source),
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

    async def set_payment_verified(self, payment_id: int) -> None:
        await self._db.execute(
            "UPDATE payments SET verified = 1 WHERE id = ?", (payment_id,)
        )
        await self._db.commit()

    async def set_payment_note(self, payment_id: int, note: str) -> None:
        await self._db.execute(
            "UPDATE payments SET note = ? WHERE id = ?", (note[:500], payment_id)
        )
        await self._db.commit()

    async def mark_error(self, payment_id: int, note: str) -> None:
        await self._db.execute(
            "UPDATE payments SET status = 'error', note = ? WHERE id = ?", (note[:500], payment_id)
        )
        await self._db.commit()

    async def latest_pending_card_payment(self, tg_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM payments WHERE tg_id = ? AND provider = 'card' "
            "AND status = 'pending' ORDER BY id DESC LIMIT 1",
            (tg_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

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

    # ── платежи пользователя, рефералы ─────────────────────────────────

    async def payments_for_user(self, tg_id: int, limit: int = 5) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM payments WHERE tg_id = ? ORDER BY id DESC LIMIT ?",
            (tg_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def delivered_paid_count(self, tg_id: int) -> int:
        """Сколько РЕАЛЬНЫХ оплат (не подарки/промо/триал) уже у пользователя."""
        async with self._db.execute(
            "SELECT COUNT(*) FROM payments WHERE tg_id = ? AND status IN ('paid','delivered') "
            "AND provider IN ('stars','cryptobot','yookassa')",
            (tg_id,),
        ) as cur:
            return (await cur.fetchone())[0]

    async def count_referrals(self, referrer_tg_id: int) -> int:
        async with self._db.execute(
            "SELECT COUNT(*) FROM bot_users WHERE referred_by = ?", (str(referrer_tg_id),)
        ) as cur:
            return (await cur.fetchone())[0]

    async def paid_referrals(self, referrer_tg_id: int) -> int:
        async with self._db.execute(
            """
            SELECT COUNT(DISTINCT p.tg_id) FROM payments p
            JOIN bot_users b ON b.tg_id = p.tg_id
            WHERE b.referred_by = ? AND p.status IN ('paid','delivered')
              AND p.provider IN ('stars','cryptobot','yookassa')
            """,
            (str(referrer_tg_id),),
        ) as cur:
            return (await cur.fetchone())[0]

    async def ref_bonus_days_total(self, referrer_tg_id: int) -> float:
        async with self._db.execute(
            "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM payments "
            "WHERE tg_id = ? AND provider = 'refbonus' AND status = 'delivered'",
            (referrer_tg_id,),
        ) as cur:
            return (await cur.fetchone())[0]

    async def referrals_total(self) -> int:
        async with self._db.execute(
            "SELECT COUNT(*) FROM bot_users WHERE referred_by IS NOT NULL"
        ) as cur:
            return (await cur.fetchone())[0]

    # ── тикеты поддержки ───────────────────────────────────────────────

    async def create_ticket(self, tg_id: int) -> int:
        cur = await self._db.execute(
            "INSERT INTO tickets (tg_id, status, created_at) VALUES (?, 'open', ?)",
            (tg_id, utcnow().isoformat()),
        )
        await self._db.commit()
        return cur.lastrowid

    async def get_ticket(self, ticket_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def open_ticket_for_user(self, tg_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM tickets WHERE tg_id = ? AND status != 'closed' "
            "ORDER BY id DESC LIMIT 1",
            (tg_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def open_tickets(self, limit: int = 20) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM tickets WHERE status != 'closed' ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def add_ticket_message(
        self, ticket_id: int, role: str, tg_id: int,
        chat_id: int | None = None, message_id: int | None = None,
    ) -> None:
        await self._db.execute(
            "INSERT INTO ticket_messages (ticket_id, role, tg_id, chat_id, message_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ticket_id, role, tg_id, chat_id, message_id, utcnow().isoformat()),
        )
        await self._db.execute(
            "UPDATE tickets SET updated_at = ? WHERE id = ?",
            (utcnow().isoformat(), ticket_id),
        )
        await self._db.commit()

    async def set_ticket_status(self, ticket_id: int, status: str) -> None:
        closed = utcnow().isoformat() if status == "closed" else None
        await self._db.execute(
            "UPDATE tickets SET status = ?, closed_at = COALESCE(?, closed_at) WHERE id = ?",
            (status, closed, ticket_id),
        )
        await self._db.commit()

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
