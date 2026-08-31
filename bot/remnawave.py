"""Асинхронный клиент REST API Remnawave (https://remna.st).

Ответы панели завёрнуты в {"response": ...} — unwrap делается здесь,
наружу отдаются "чистые" dict / list.
"""
from __future__ import annotations

from typing import Any

import httpx

from .config import Config
from .utils import to_iso


class RemnaError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class RemnawaveClient:
    def __init__(self, cfg: Config):
        self._base = cfg.panel_url
        self._prefix = cfg.api_prefix.rstrip("/")
        self._sub_domain = (cfg.sub_page_domain or "").rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self._base,
            headers={
                "Authorization": f"Bearer {cfg.api_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "tg-vpn-shop-bot/1.0",
            },
            timeout=httpx.Timeout(30.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(
        self, method: str, path: str, *, json: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        try:
            resp = await self._http.request(method, self._prefix + path, json=json, params=params)
        except httpx.HTTPError as e:
            raise RemnaError(f"Панель недоступна: {e.__class__.__name__}: {e}") from e
        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                msg = body.get("message") or body.get("error") or body
                if isinstance(msg, list):
                    # NestJS ValidationPipe: массив требований по полям
                    detail = "; ".join(str(m) for m in msg)[:500]
                elif isinstance(msg, str):
                    detail = msg
                else:
                    detail = str(msg)[:500]
                # некоторые фильтры прячут детали — добавим сырой ответ
                if "validation" in detail.lower() and body.get("message") == detail:
                    raw = str(body)[:500]
                    if raw != detail:
                        detail = f"{detail} | raw: {raw}"
            except Exception:
                detail = resp.text[:500]
            raise RemnaError(f"HTTP {resp.status_code}: {detail}", status=resp.status_code)
        if not resp.content:
            return {}
        data = resp.json()
        if isinstance(data, dict) and set(data.keys()) == {"response"}:
            return data["response"]
        return data

    # ── пользователи ───────────────────────────────────────────────────

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict | None:
        data = await self._request("GET", f"/users/by-telegram-id/{telegram_id}")
        if isinstance(data, dict):
            data = data.get("users") or data.get("response") or [data]
        if isinstance(data, list) and data:
            return data[0]
        return None

    async def get_user(self, uuid: str) -> dict:
        return await self._request("GET", f"/users/{uuid}")

    async def get_user_by_username(self, username: str) -> dict | None:
        try:
            return await self._request("GET", f"/users/by-username/{username}")
        except RemnaError as e:
            if e.status == 404:
                return None
            raise

    async def create_user(
        self,
        username: str,
        *,
        expire_at: str,
        squad_uuids: list[str],
        telegram_id: int | None = None,
        email: str | None = None,
        description: str | None = None,
        tag: str | None = None,
        traffic_limit_bytes: int | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "username": username,
            "expireAt": expire_at,
            "activeInternalSquads": squad_uuids,
        }
        if telegram_id:
            payload["telegramId"] = telegram_id
        if email:
            payload["email"] = email
        if description:
            payload["description"] = description
        if tag:
            payload["tag"] = tag
        if traffic_limit_bytes:
            payload["trafficLimitBytes"] = traffic_limit_bytes
            payload["trafficLimitStrategy"] = "NO_RESET"
        return await self._request("POST", "/users", json=payload)

    async def update_user(self, uuid: str, **fields: Any) -> dict:
        body = {"uuid": uuid, **fields}
        return await self._request("PATCH", "/users", json=body)

    async def set_expire(self, uuid: str, dt) -> dict:
        return await self.update_user(uuid, expireAt=to_iso(dt))

    async def enable_user(self, uuid: str) -> dict:
        return await self._request("POST", f"/users/{uuid}/actions/enable")

    async def disable_user(self, uuid: str) -> dict:
        return await self._request("POST", f"/users/{uuid}/actions/disable")

    async def reset_traffic(self, uuid: str) -> dict:
        return await self._request("POST", f"/users/{uuid}/actions/reset-traffic")

    async def iter_users(self, page_size: int = 500):
        """Обходит всех пользователей панели постранично."""
        start = 0
        while True:
            data = await self._request(
                "GET", "/users", params={"start": start, "size": page_size}
            )
            if isinstance(data, dict):
                users = data.get("users") or []
            elif isinstance(data, list):
                users = data
            else:
                users = []
            if not users:
                break
            for u in users:
                yield u
            if len(users) < page_size:
                break
            start += page_size

    async def users_count(self) -> dict:
        """total и число активных (лёгкий запрос + пагинация)."""
        data = await self._request("GET", "/users", params={"start": 0, "size": 1})
        total = None
        if isinstance(data, dict):
            total = data.get("total")
        active = 0
        scanned = 0
        async for u in self.iter_users():
            scanned += 1
            if str(u.get("status", "")).upper() == "ACTIVE":
                active += 1
        return {"total": total if total is not None else scanned, "active": active}

    # ── инфраструктура ─────────────────────────────────────────────────

    async def list_internal_squads(self) -> list[dict]:
        data = await self._request("GET", "/internal-squads")
        if isinstance(data, dict):
            data = data.get("internalSquads") or data.get("squads") or []
        return data if isinstance(data, list) else []

    async def nodes_usage(self) -> list[dict]:
        """Статистика нод (онлайн-юзеры/трафик) — зависит от версии панели.

        Возвращает список dict; при отсутствии эндпоинта — пустой список.
        """
        try:
            data = await self._request("GET", "/nodes/usage")
        except RemnaError:
            return []
        if isinstance(data, dict):
            data = data.get("usage") or data.get("response") or data.get("items") or []
        return data if isinstance(data, list) else []

    async def list_nodes(self) -> list[dict]:
        data = await self._request("GET", "/nodes")
        if isinstance(data, dict):
            data = data.get("nodes") or []
        return data if isinstance(data, list) else []

    # ── ссылка на подписку ─────────────────────────────────────────────

    def build_sub_url(self, user: dict) -> str:
        # SUB_PAGE_DOMAIN задан явно — строим ссылку сами (приоритет над панелью):
        # полезно, когда поднята страница подписок и хочется красивые ссылки
        short = user.get("shortUuid") or user.get("short_uuid")
        if self._sub_domain and short:
            return f"{self._sub_domain}/{short}"
        url = user.get("subscriptionUrl")
        if url:
            return str(url).strip()
        raise RemnaError(
            "Не удалось получить ссылку на подписку: "
            "задайте SUB_PAGE_DOMAIN в .env или настройте subscription page в панели."
        )

    async def health(self) -> dict:
        """Быстрая проверка доступности панели и токена."""
        await self._request("GET", "/nodes")
        return {"ok": True}
