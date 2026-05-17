"""Webhook receiver for NakoPay event notifications.

Instead of polling the API for invoice status changes, merchants can configure
a webhook URL pointing to this handler. Events are forwarded to a Telegram
chat as formatted messages.

Run alongside the bot or as a standalone FastAPI/Starlette app:
    uvicorn nakopay_telegram.webhook:app --port 8443
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx

log = logging.getLogger("nakopay_telegram.webhook")

TG_API = "https://api.telegram.org"

# env
WEBHOOK_SECRET = os.environ.get("NAKOPAY_WEBHOOK_SECRET", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
NOTIFY_CHAT_ID = os.environ.get("NAKOPAY_NOTIFY_CHAT_ID", "")


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


STATUS_EMOJI = {
    "invoice.paid": "✅",
    "invoice.expired": "⏰",
    "invoice.canceled": "❌",
    "invoice.underpaid": "⚠️",
    "invoice.overpaid": "💰",
    "invoice.confirmed": "🔒",
}


def format_event(event: str, data: dict[str, Any]) -> str:
    emoji = STATUS_EMOJI.get(event, "📋")
    invoice_id = data.get("id") or data.get("invoice_id") or "?"
    amount = data.get("amount") or "?"
    currency = data.get("currency") or ""
    return (
        f"{emoji} *{event}*\n"
        f"Invoice: `{invoice_id}`\n"
        f"Amount: {amount} {currency}"
    )


async def notify_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not NOTIFY_CHAT_ID:
        log.warning("TELEGRAM_BOT_TOKEN or NAKOPAY_NOTIFY_CHAT_ID not set - skipping notification")
        return
    url = f"{TG_API}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={
            "chat_id": NOTIFY_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        })


# --------------------------------------------------------------------------- #
# ASGI app (Starlette-compatible)
# --------------------------------------------------------------------------- #
try:
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    async def handle_webhook(request: Request) -> Response:
        body = await request.body()
        sig = request.headers.get("x-nakopay-signature", "")

        if WEBHOOK_SECRET and not verify_signature(body, sig, WEBHOOK_SECRET):
            return JSONResponse({"error": "invalid signature"}, status_code=401)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid json"}, status_code=400)

        event = payload.get("event") or payload.get("type") or "unknown"
        data = payload.get("data") or payload
        text = format_event(event, data)
        await notify_telegram(text)
        return JSONResponse({"ok": True})

    async def health(_request: Request) -> Response:
        return JSONResponse({"status": "ok", "service": "nakopay-telegram-webhook"})

    app = Starlette(
        routes=[
            Route("/webhook", handle_webhook, methods=["POST"]),
            Route("/health", health, methods=["GET"]),
        ]
    )
except ImportError:
    app = None  # type: ignore[assignment]
    log.info("Starlette not installed - webhook ASGI app unavailable")
