"""Long-polling Telegram bot for NakoPay.

v0.1.0 ships in single-merchant mode: every chat that talks to the bot uses
the same `NAKOPAY_API_KEY` configured in the operator's environment. This is
exactly how a small business would self-host: one bot per merchant.

Run with `python -m nakopay_telegram.bot` after setting env vars from
.env.example. See README Appendix A for deployment.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shlex
from typing import Any

import httpx

from .config import Config, load
from .nakopay_client import NakoPayClient, NakoPayError


log = logging.getLogger("nakopay_telegram")

TG_API = "https://api.telegram.org"

HELP_TEXT = (
    "*NakoPay bot*\n"
    "/invoice <amount> <currency> [for \"desc\"] - create a payable invoice\n"
    "/last - 5 most recent invoices\n"
    "/help - show this message\n"
    "\n"
    "_/connect, /disconnect, /balance are roadmap items - see README._"
)

NOT_YET_TEXT = (
    "Not available yet. This bot runs in single-merchant mode (one bot per "
    "merchant, configured via the operator's `NAKOPAY_API_KEY` env). "
    "Multi-merchant linking and balance reporting are planned for a future release."
)

INVOICE_RE = re.compile(
    r"""^\s*
        (?P<amount>\d+(?:\.\d+)?)\s+
        (?P<currency>[A-Za-z]{3,5})
        (?:\s+for\s+(?P<desc>.+))?
        \s*$""",
    re.VERBOSE,
)


# --------------------------------------------------------------------------- #
# Telegram primitives
# --------------------------------------------------------------------------- #
class Telegram:
    def __init__(self, token: str, timeout: int) -> None:
        self._base = f"{TG_API}/bot{token}"
        self._timeout = timeout
        self._offset: int | None = None

    async def get_updates(self) -> list[dict]:
        params: dict[str, Any] = {"timeout": self._timeout}
        if self._offset is not None:
            params["offset"] = self._offset
        async with httpx.AsyncClient(timeout=self._timeout + 10) as client:
            r = await client.get(f"{self._base}/getUpdates", params=params)
        r.raise_for_status()
        body = r.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram error: {body}")
        updates = body.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    async def send(self, chat_id: int, text: str, *, markdown: bool = True) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if markdown:
            payload["parse_mode"] = "Markdown"
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{self._base}/sendMessage", json=payload)
        if r.status_code >= 400:
            log.warning("Telegram sendMessage failed: %s %s", r.status_code, r.text)


# --------------------------------------------------------------------------- #
# Bot core
# --------------------------------------------------------------------------- #
class Bot:
    def __init__(self, cfg: Config, tg: Telegram) -> None:
        self._cfg = cfg
        self._tg = tg

    def _client(self) -> NakoPayClient:
        # Single-merchant mode: api_key is guaranteed present by config.load().
        return NakoPayClient(self._cfg.api_base, self._cfg.api_key)  # type: ignore[arg-type]

    async def handle(self, update: dict) -> None:
        msg = update.get("message") or update.get("channel_post")
        if not msg:
            return
        text = (msg.get("text") or "").strip()
        chat_id = msg["chat"]["id"]
        if not text.startswith("/"):
            return

        # Strip @botname suffix that Telegram appends in groups
        cmd, _, rest = text.partition(" ")
        cmd = cmd.split("@", 1)[0].lower()
        rest = rest.strip()

        try:
            if cmd == "/start":
                await self._tg.send(
                    chat_id,
                    "Welcome to *NakoPay*. Try `/invoice 25 USD for \"Coffee\"` "
                    "or `/help` to see all commands.",
                )
            elif cmd == "/help":
                await self._tg.send(chat_id, HELP_TEXT)
            elif cmd == "/invoice":
                await self._cmd_invoice(chat_id, rest)
            elif cmd == "/last":
                await self._cmd_last(chat_id)
            elif cmd in ("/connect", "/disconnect", "/balance"):
                await self._tg.send(chat_id, NOT_YET_TEXT)
        except NakoPayError as e:
            await self._tg.send(chat_id, f"NakoPay API error: {e}")
        except Exception:  # noqa: BLE001
            log.exception("Unhandled error in command %s", cmd)
            await self._tg.send(chat_id, "Something went wrong. Try again in a moment.")

    # ----- commands -----
    async def _cmd_invoice(self, chat_id: int, rest: str) -> None:
        m = INVOICE_RE.match(rest)
        if not m:
            await self._tg.send(
                chat_id,
                "Usage: `/invoice 25 USD` or `/invoice 0.001 BTC for \"Coffee\"`.",
            )
            return
        amount = float(m.group("amount"))
        currency = m.group("currency").upper()
        desc_raw = (m.group("desc") or "").strip()
        desc: str | None = None
        if desc_raw:
            try:
                parts = shlex.split(desc_raw)
                desc = " ".join(parts) if parts else desc_raw
            except ValueError:
                desc = desc_raw

        link = await self._client().create_payment_link(amount, currency, desc)
        url = link.get("url") or link.get("checkout_url") or link.get("hosted_url")
        invoice_id = link.get("id") or "(no id)"
        text = (
            f"*Invoice {invoice_id}* - {amount} {currency}\n"
            + (f"_{desc}_\n" if desc else "")
            + (f"Pay: {url}" if url else "Created.")
        )
        await self._tg.send(chat_id, text)

    async def _cmd_last(self, chat_id: int) -> None:
        invoices = await self._client().list_invoices(limit=5)
        if not invoices:
            await self._tg.send(chat_id, "No invoices yet.")
            return
        lines = ["*Last 5 invoices*"]
        for inv in invoices:
            lines.append(
                f"- `{inv.get('id', '?')}` {inv.get('amount', '?')} "
                f"{inv.get('currency', '')} - {inv.get('status', '?')}"
            )
        await self._tg.send(chat_id, "\n".join(lines))


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
async def _run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load()
    log.info(
        "Starting NakoPay Telegram bot (api_base=%s, mode=single-merchant)",
        cfg.api_base,
    )
    tg = Telegram(cfg.telegram_token, cfg.poll_timeout)
    bot = Bot(cfg, tg)

    backoff = 1
    while True:
        try:
            updates = await tg.get_updates()
            backoff = 1
            for u in updates:
                await bot.handle(u)
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            log.warning("Network error: %s. Retrying in %ds.", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except Exception:  # noqa: BLE001
            log.exception("Fatal error in poll loop")
            await asyncio.sleep(5)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
