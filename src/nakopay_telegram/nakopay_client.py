"""Thin async wrapper around the NakoPay REST API.

v0.2.0 - Added balance, rates, refund endpoints.

Uses an `sk_live_*` / `sk_test_*` merchant key as a Bearer token. Endpoints
match the canonical Supabase Edge Functions deployed at
https://daslrxpkbkqrbnjwouiq.supabase.co/functions/v1/.
"""
from __future__ import annotations

import secrets
from typing import Any

import httpx


class NakoPayError(Exception):
    """Raised when the NakoPay API returns a non-2xx response."""

    def __init__(self, status: int, message: str, payload: Any = None) -> None:
        super().__init__(f"[{status}] {message}")
        self.status = status
        self.payload = payload


class NakoPayClient:
    VERSION = "2025-04-20"

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 15.0) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self, *, idempotent: bool = False) -> dict[str, str]:
        h: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "nakopay-telegram/0.2.0",
            "X-NakoPay-Version": self.VERSION,
        }
        if idempotent:
            h["Idempotency-Key"] = f"idem_{secrets.token_hex(16)}"
        return h

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base}{path}"
        idempotent = method.upper() == "POST"
        headers = self._headers(idempotent=idempotent)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msg = (
                    body.get("error", {}).get("message")
                    or body.get("message")
                    or resp.text
                )
            except Exception:
                body, msg = None, resp.text
            raise NakoPayError(resp.status_code, msg, body)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # ----- payment links -----
    async def create_payment_link(
        self,
        amount: float,
        currency: str,
        description: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "amount": amount,
            "currency": currency.upper(),
        }
        if description:
            body["description"] = description
        return await self._request("POST", "/payment-links", json=body)

    # ----- invoices -----
    async def list_invoices(self, limit: int = 5) -> list[dict]:
        data = await self._request("GET", f"/invoices-list?limit={limit}")
        if isinstance(data, dict):
            return data.get("data") or data.get("invoices") or [data]
        return data or []

    async def get_invoice(self, invoice_id: str) -> dict:
        return await self._request("GET", f"/invoices/{invoice_id}")

    # ----- balance -----
    async def get_balance(self) -> Any:
        return await self._request("GET", "/balance")

    # ----- rates -----
    async def get_rates(self, currency: str = "USD") -> Any:
        return await self._request("GET", f"/rates?currency={currency}")

    # ----- refund -----
    async def refund_invoice(self, invoice_id: str) -> dict:
        return await self._request("POST", f"/invoices/{invoice_id}/refund")
