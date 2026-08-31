"""Платёжные провайдеры: CryptoBot (Crypto Pay API) и ЮKassa.

Telegram Stars обрабатывается нативно внутри aiogram (см. handlers/buy.py).
"""
from __future__ import annotations

import uuid as uuidlib

import httpx

CRYPTOBOT_BASE = "https://pay.crypt.bot/api"
CRYPTOBOT_TESTNET_BASE = "https://testnet-pay.crypt.bot/api"


class ProviderError(Exception):
    pass


class CryptoBotProvider:
    name = "cryptobot"

    def __init__(self, token: str, *, testnet: bool = False):
        self._http = httpx.AsyncClient(
            base_url=CRYPTOBOT_TESTNET_BASE if testnet else CRYPTOBOT_BASE,
            headers={"Crypto-Pay-API-Token": token},
            timeout=30.0,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, **params) -> dict:
        try:
            resp = await self._http.post(f"/{method}", json=params)
        except httpx.HTTPError as e:
            raise ProviderError(f"CryptoBot недоступен: {e}") from e
        data = resp.json()
        if not data.get("ok"):
            raise ProviderError(f"CryptoBot: {data.get('error') or data}")
        return data["result"]

    async def create_invoice(
        self, *, amount: float, description: str, payload: str, ttl_seconds: int = 3600
    ) -> dict:
        """Возвращает dict с invoice_id, bot_invoice_url / pay_url и т.п."""
        return await self._call(
            "createInvoice",
            asset="USDT",
            amount=f"{amount:.2f}",
            description=description,
            payload=payload,
            paidBtnName="callback",
            allowComments=False,
            allowAnonymous=True,
            expiresIn=ttl_seconds,
        )

    @staticmethod
    def pay_url(invoice: dict) -> str | None:
        return (
            invoice.get("bot_invoice_url")
            or invoice.get("pay_url")
            or invoice.get("mini_app_invoice_url")
            or invoice.get("web_app_invoice_url")
        )

    async def check_invoice(self, invoice_id: str) -> str:
        """Статус счёта: active | paid | expired (прочее трактуем как active)."""
        result = await self._call("getInvoices", invoiceIds=invoice_id, status="all")
        items = result.get("items") or []
        for item in items:
            if str(item.get("invoice_id")) == str(invoice_id):
                status = item.get("status")
                if status == "paid":
                    return "paid"
                if status in ("expired", "canceled"):
                    return "expired"
        return "active"

    async def health(self) -> bool:
        await self._call("getMe")
        return True


class YooKassaProvider:
    name = "yookassa"

    def __init__(self, shop_id: str, secret: str):
        self._shop_id = shop_id
        self._http = httpx.AsyncClient(
            base_url="https://api.yookassa.ru/v3",
            auth=(shop_id, secret),
            timeout=30.0,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def create_payment(
        self, *, amount_rub: float, description: str, return_url: str, metadata: str
    ) -> dict:
        body = {
            "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description[:128],
            "metadata": {"payload": metadata[:128]},
        }
        try:
            resp = await self._http.post(
                "/payments",
                json=body,
                headers={"Idempotence-Key": str(uuidlib.uuid4())},
            )
        except httpx.HTTPError as e:
            raise ProviderError(f"ЮKassa недоступна: {e}") from e
        if resp.status_code >= 400:
            raise ProviderError(f"ЮKassa HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    @staticmethod
    def confirmation_url(payment: dict) -> str | None:
        return (payment.get("confirmation") or {}).get("confirmation_url")

    async def check_payment(self, payment_id: str) -> str:
        try:
            resp = await self._http.get(f"/payments/{payment_id}")
        except httpx.HTTPError as e:
            raise ProviderError(f"ЮKassa недоступна: {e}") from e
        if resp.status_code >= 400:
            raise ProviderError(f"ЮKassa HTTP {resp.status_code}")
        status = resp.json().get("status")
        if status == "succeeded":
            return "paid"
        if status == "canceled":
            return "canceled"
        return "pending"
