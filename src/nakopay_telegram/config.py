"""Configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass

_SUPABASE_BASE = "https://daslrxpkbkqrbnjwouiq.supabase.co/functions/v1"


@dataclass(frozen=True)
class Config:
    telegram_token: str
    api_key: str | None
    api_base: str
    poll_timeout: int
    data_dir: str


def load() -> Config:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")
    return Config(
        telegram_token=token,
        api_key=os.environ.get("NAKOPAY_API_KEY"),
        api_base=os.environ.get("NAKOPAY_API_BASE", _SUPABASE_BASE),
        poll_timeout=int(os.environ.get("POLL_TIMEOUT", "30")),
        data_dir=os.environ.get("NAKOPAY_DATA_DIR", "/data"),
    )
