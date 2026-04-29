"""SQLite-backed mapping of Telegram chat IDs to NakoPay merchant API keys.

Used in multi-merchant mode (NAKOPAY_API_KEY is unset). The merchant runs
`/connect <link_token>` in a chat with the bot. The bot exchanges the link
token with the NakoPay API and stores the returned merchant API key here.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_links (
  chat_id     INTEGER PRIMARY KEY,
  merchant_id TEXT NOT NULL,
  api_key     TEXT NOT NULL,
  linked_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Store:
    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=10, isolation_level=None)
        try:
            yield conn
        finally:
            conn.close()

    def link(self, chat_id: int, merchant_id: str, api_key: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO chat_links(chat_id, merchant_id, api_key) "
                "VALUES (?, ?, ?)",
                (chat_id, merchant_id, api_key),
            )

    def unlink(self, chat_id: int) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM chat_links WHERE chat_id = ?", (chat_id,))
            return cur.rowcount > 0

    def get(self, chat_id: int) -> tuple[str, str] | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT merchant_id, api_key FROM chat_links WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return (row[0], row[1]) if row else None
