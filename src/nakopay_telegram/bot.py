"""Long-polling Telegram bot for NakoPay.

v0.2.0 - Full command set: /invoice, /last, /balance, /tip, /connect,
/disconnect, /rates, /refund, /export, /help.

Run with `python -m nakopay_telegram.bot` after setting env vars from
.env.example. See README Appendix A for deployment.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import shlex
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import Config, load
from .nakopay_client import NakoPayClient, NakoPayError
from .storage import Storage


log = logging.getLogger("nakopay_telegram")

TG_API = "https://api.telegram.org"

HELP_TEXT = (
    "*NakoPay bot - Commands*\n\n"
    "/invoice <amount> <currency> [for \"desc\"] - create a payable invoice\n"
    "/tip <amount> <currency> [for \"desc\"] - create a one-click tip link\n"
    "/last [N] - show N most recent invoices (default 5)\n"
    "/balance - show wallet balances\n"
    "/rates <currency> - live exchange rates\n"
    "/refund <invoice\\_id> - refund a paid invoice\n"
    "/export - export invoices as CSV\n"
    "/connect <api\\_key> - link your NakoPay merchant key (multi-merchant)\n"
    "/disconnect - unlink your merchant key\n"
    "/status - bot and connection status\n"
    "/help - show this message"
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

    async def send_document(
        self, chat_id: int, filename: str, content: bytes, caption: str = ""
    ) -> None:
        files = {"document": (filename, content, "text/csv")}
        data: dict[str, Any] = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{self._base}/sendDocument", data=data, files=files)
        if r.status_code >= 400:
            log.warning("Telegram sendDocument failed: %s %s", r.status_code, r.text)


# --------------------------------------------------------------------------- #
# Bot core
# --------------------------------------------------------------------------- #
class Bot:
    def __init__(self, cfg: Config, tg: Telegram, storage: Storage) -> None:
        self._cfg = cfg
        self._tg = tg
        self._storage = storage

    def _client(self, chat_id: int | None = None) -> NakoPayClient:
        """Return a NakoPayClient.

        In multi-merchant mode, looks up a per-chat key first. Falls back to
        the operator's global key.
        """
        key = None
        if chat_id is not None:
            key = self._storage.get_key(chat_id)
        if key is None:
            key = self._cfg.api_key
        if key is None:
            raise NakoPayError(
                401,
                "No API key configured. Use /connect <key> or set NAKOPAY_API_KEY.",
            )
        return NakoPayClient(self._cfg.api_base, key)

    async def handle(self, update: dict) -> None:
        msg = update.get("message") or update.get("channel_post")
        if not msg:
            return
        text = (msg.get("text") or "").strip()
        chat_id: int = msg["chat"]["id"]
        if not text.startswith("/"):
            return

        cmd, _, rest = text.partition(" ")
        cmd = cmd.split("@", 1)[0].lower()
        rest = rest.strip()

        try:
            handler = {
                "/start": self._cmd_start,
                "/help": self._cmd_help,
                "/invoice": self._cmd_invoice,
                "/tip": self._cmd_tip,
                "/last": self._cmd_last,
                "/balance": self._cmd_balance,
                "/rates": self._cmd_rates,
                "/refund": self._cmd_refund,
                "/export": self._cmd_export,
                "/connect": self._cmd_connect,
                "/disconnect": self._cmd_disconnect,
                "/status": self._cmd_status,
            }.get(cmd)
            if handler:
                await handler(chat_id, rest)
        except NakoPayError as e:
            await self._tg.send(chat_id, f"NakoPay API error: {e}")
        except Exception:  # noqa: BLE001
            log.exception("Unhandled error in command %s", cmd)
            await self._tg.send(chat_id, "Something went wrong. Try again in a moment.")

    # ----- commands -----

    async def _cmd_start(self, chat_id: int, _rest: str) -> None:
        await self._tg.send(
            chat_id,
            "Welcome to *NakoPay*! Try `/invoice 25 USD for \"Coffee\"` "
            "or `/help` to see all commands.",
        )

    async def _cmd_help(self, chat_id: int, _rest: str) -> None:
        await self._tg.send(chat_id, HELP_TEXT)

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
        desc = _parse_desc(m.group("desc"))

        link = await self._client(chat_id).create_payment_link(amount, currency, desc)
        url = link.get("url") or link.get("checkout_url") or link.get("hosted_url")
        invoice_id = link.get("id") or "(no id)"
        text = (
            f"*Invoice {invoice_id}* - {amount} {currency}\n"
            + (f"_{desc}_\n" if desc else "")
            + (f"Pay here: {url}" if url else "Created.")
        )
        await self._tg.send(chat_id, text)

    async def _cmd_tip(self, chat_id: int, rest: str) -> None:
        m = INVOICE_RE.match(rest)
        if not m:
            await self._tg.send(
                chat_id,
                "Usage: `/tip 5 USD` or `/tip 0.0005 BTC for \"Thanks!\"`.",
            )
            return
        amount = float(m.group("amount"))
        currency = m.group("currency").upper()
        desc = _parse_desc(m.group("desc")) or "Tip"

        link = await self._client(chat_id).create_payment_link(
            amount, currency, f"[Tip] {desc}"
        )
        url = link.get("url") or link.get("checkout_url") or link.get("hosted_url")
        text = f"*Tip link* - {amount} {currency}\n" + (
            f"Send to anyone: {url}" if url else "Created."
        )
        await self._tg.send(chat_id, text)

    async def _cmd_last(self, chat_id: int, rest: str) -> None:
        try:
            limit = max(1, min(int(rest), 20)) if rest else 5
        except ValueError:
            limit = 5
        invoices = await self._client(chat_id).list_invoices(limit=limit)
        if not invoices:
            await self._tg.send(chat_id, "No invoices yet.")
            return
        lines = [f"*Last {len(invoices)} invoices*"]
        for inv in invoices:
            status_emoji = {"paid": "✅", "expired": "⏰", "pending": "⏳"}.get(
                inv.get("status", ""), "❓"
            )
            lines.append(
                f"{status_emoji} `{inv.get('id', '?')}` "
                f"{inv.get('amount', '?')} {inv.get('currency', '')} "
                f"- {inv.get('status', '?')}"
            )
        await self._tg.send(chat_id, "\n".join(lines))

    async def _cmd_balance(self, chat_id: int, _rest: str) -> None:
        balances = await self._client(chat_id).get_balance()
        if not balances:
            await self._tg.send(chat_id, "No balance data available.")
            return
        lines = ["*Wallet balances*"]
        if isinstance(balances, dict):
            items = balances.get("data") or balances.get("balances") or [balances]
            if isinstance(items, dict):
                items = [items]
        else:
            items = balances
        for b in items:
            coin = b.get("currency") or b.get("coin") or "?"
            avail = b.get("available") or b.get("balance") or b.get("amount") or "0"
            lines.append(f"- *{coin}*: {avail}")
        await self._tg.send(chat_id, "\n".join(lines))

    async def _cmd_rates(self, chat_id: int, rest: str) -> None:
        currency = rest.strip().upper() or "USD"
        rates = await self._client(chat_id).get_rates(currency)
        if not rates:
            await self._tg.send(chat_id, f"No rate data for {currency}.")
            return
        lines = [f"*Rates ({currency})*"]
        items = rates if isinstance(rates, list) else rates.get("data", [rates])
        for r in items[:10]:
            coin = r.get("coin") or r.get("currency") or "?"
            price = r.get("rate") or r.get("price") or "?"
            lines.append(f"- *{coin}*: {price} {currency}")
        await self._tg.send(chat_id, "\n".join(lines))

    async def _cmd_refund(self, chat_id: int, rest: str) -> None:
        invoice_id = rest.strip()
        if not invoice_id:
            await self._tg.send(chat_id, "Usage: `/refund <invoice_id>`")
            return
        result = await self._client(chat_id).refund_invoice(invoice_id)
        status = result.get("status") or "initiated"
        await self._tg.send(chat_id, f"Refund for `{invoice_id}`: *{status}*")

    async def _cmd_export(self, chat_id: int, _rest: str) -> None:
        invoices = await self._client(chat_id).list_invoices(limit=100)
        if not invoices:
            await self._tg.send(chat_id, "No invoices to export.")
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "amount", "currency", "status", "created_at"])
        for inv in invoices:
            writer.writerow([
                inv.get("id", ""),
                inv.get("amount", ""),
                inv.get("currency", ""),
                inv.get("status", ""),
                inv.get("created_at", ""),
            ])
        now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"nakopay_invoices_{now}.csv"
        await self._tg.send_document(
            chat_id,
            filename,
            buf.getvalue().encode("utf-8"),
            caption="Here are your invoices.",
        )

    async def _cmd_connect(self, chat_id: int, rest: str) -> None:
        key = rest.strip()
        if not key or not (key.startswith("sk_live_") or key.startswith("sk_test_")):
            await self._tg.send(
                chat_id,
                "Usage: `/connect sk_live_...` or `/connect sk_test_...`\n"
                "Find your key at nakopay.com/dashboard/api-keys",
            )
            return
        self._storage.set_key(chat_id, key)
        mode = "test" if key.startswith("sk_test_") else "live"
        await self._tg.send(
            chat_id,
            f"Connected in *{mode}* mode. Your key is stored locally. "
            "Use /disconnect to remove it.",
        )

    async def _cmd_disconnect(self, chat_id: int, _rest: str) -> None:
        self._storage.delete_key(chat_id)
        await self._tg.send(
            chat_id,
            "Disconnected. The bot will use the operator's default key (if set).",
        )

    async def _cmd_status(self, chat_id: int, _rest: str) -> None:
        has_own_key = self._storage.get_key(chat_id) is not None
        has_global = self._cfg.api_key is not None
        mode = "multi-merchant (your key)" if has_own_key else (
            "single-merchant (operator key)" if has_global else "not connected"
        )
        await self._tg.send(
            chat_id,
            f"*Status*\nMode: {mode}\nAPI: `{self._cfg.api_base}`\nBot v0.2.0",
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _parse_desc(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        parts = shlex.split(raw)
        return " ".join(parts) if parts else raw
    except ValueError:
        return raw


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
        "Starting NakoPay Telegram bot v0.2.0 (api_base=%s)",
        cfg.api_base,
    )
    tg = Telegram(cfg.telegram_token, cfg.poll_timeout)
    storage = Storage(cfg.data_dir)
    bot = Bot(cfg, tg, storage)

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
