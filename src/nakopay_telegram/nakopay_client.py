"""Thin async wrapper around the NakoPay REST API.

Uses an `sk_live_*` / `sk_test_*` merchant key as a Bearer token. Endpoints
match the canonical Supabase Edge Functions deployed at
https://daslrxpkbkqrbnjwouiq.supabase.co/functions/v1/.
"""
from __future__ import annotations

from typing import Any

import httpx


class NakoPayError(Exception):
    """Raised when the NakoPay API returns a non-2xx response."""

    def __init__(self, status: int, message: str, payload: Any = None) -> None:
        super().__init__(f"[{status}] {message}")
        self.status = status
        self.payload = payload


class NakoPayClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 15.0) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "nakopay-telegram/0.1.0",
        }
        self._timeout = timeout

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.request(method, url, headers=self._headers, **kwargs)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msg = body.get("error", {}).get("message") or body.get("message") or resp.text
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
            return data.get("data") or data.get("invoices") or []
        return data or []
