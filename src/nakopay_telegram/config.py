"""Env-driven config for the bot."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    telegram_token: str
    api_base: str
    api_key: str | None  # required for v0.1.0 (single-merchant mode)
    poll_timeout: int
    db_path: str

    @property
    def single_merchant_mode(self) -> bool:
        # v0.1.0 always runs in single-merchant mode. Multi-merchant /connect
        # flow is reserved for a future release once the backend exposes a
        # link-token exchange endpoint.
        return True


def load() -> Config:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is required. Get one from @BotFather "
            "(https://t.me/BotFather) and set it in your env or .env file."
        )
    api_key = os.environ.get("NAKOPAY_API_KEY", "").strip() or None
    if not api_key:
        raise RuntimeError(
            "NAKOPAY_API_KEY is required (sk_live_... or sk_test_...). "
            "Create one at https://nakopay.com/dashboard/api-keys."
        )
    api_base = os.environ.get(
        "NAKOPAY_API_BASE",
        "https://daslrxpkbkqrbnjwouiq.supabase.co/functions/v1",
    ).rstrip("/")
    poll_timeout = int(os.environ.get("TELEGRAM_POLL_TIMEOUT", "30"))
    db_path = os.environ.get("NAKOPAY_TG_DB_PATH", "./nakopay-telegram.sqlite3")
    return Config(
        telegram_token=token,
        api_base=api_base,
        api_key=api_key,
        poll_timeout=poll_timeout,
        db_path=db_path,
    )
