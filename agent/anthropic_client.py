"""Minimal Anthropic Messages API client without hardcoded secrets."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class AnthropicClientError(RuntimeError):
    pass


class AnthropicClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        api_url: str = "https://api.anthropic.com/v1/messages",
        timeout: float = 30,
    ):
        self.api_key = api_key
        self.model = model
        self.api_url = api_url
        self.timeout = timeout

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.model)

    def complete(self, system: str, messages: list[dict[str, str]], max_tokens: int = 900) -> str:
        if not self.ready:
            raise AnthropicClientError("ANTHROPIC_API_KEY is required")

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        req = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AnthropicClientError(f"Anthropic request failed: HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise AnthropicClientError(f"Anthropic unavailable: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AnthropicClientError("Anthropic returned invalid JSON") from exc

        parts = data.get("content") or []
        text_parts = [part.get("text", "") for part in parts if part.get("type") == "text"]
        text = "\n".join(part for part in text_parts if part).strip()
        if not text:
            raise AnthropicClientError("Anthropic returned an empty response")
        return text

