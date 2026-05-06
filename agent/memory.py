"""Small JSON memory store keyed by WhatsApp phone number."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .tools import normalize_phone


class ConversationMemory:
    def __init__(self, path: str, max_turns: int = 18):
        self.path = Path(path)
        self.max_turns = max_turns

    def load(self, phone: str) -> list[dict[str, Any]]:
        data = self._read()
        return list(data.get(self._key(phone), []))[-self.max_turns :]

    def append(self, phone: str, role: str, content: str, meta: dict[str, Any] | None = None) -> None:
        data = self._read()
        key = self._key(phone)
        turns = list(data.get(key, []))
        turns.append(
            {
                "role": role,
                "content": content,
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "meta": meta or {},
            }
        )
        data[key] = turns[-self.max_turns :]
        self._write(data)

    def clear(self, phone: str) -> None:
        data = self._read()
        data.pop(self._key(phone), None)
        self._write(data)

    @staticmethod
    def _key(phone: str) -> str:
        return normalize_phone(phone) or phone.strip()

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
        temp.replace(self.path)

