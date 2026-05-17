"""Simple JSON-file storage for per-chat API keys.

Keys are stored in a local JSON file at `<data_dir>/keys.json`. This is
suitable for single-instance deployments. For multi-instance, swap this out
for a Redis or DB adapter.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("nakopay_telegram.storage")


class Storage:
    def __init__(self, data_dir: str) -> None:
        self._path = Path(data_dir) / "keys.json"
        self._cache: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._cache = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                log.warning("Corrupt keys file at %s - starting fresh", self._path)
                self._cache = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._cache))

    def get_key(self, chat_id: int) -> str | None:
        return self._cache.get(str(chat_id))

    def set_key(self, chat_id: int, api_key: str) -> None:
        self._cache[str(chat_id)] = api_key
        self._save()

    def delete_key(self, chat_id: int) -> None:
        self._cache.pop(str(chat_id), None)
        self._save()
