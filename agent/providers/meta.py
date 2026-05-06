"""Meta WhatsApp Cloud API provider foundation."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .base import IncomingMessage, WhatsAppProviderError, query_value


class MetaWhatsAppProvider:
    name = "meta"

    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        verify_token: str,
        graph_version: str = "v20.0",
        timeout: float = 15,
    ):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.verify_token = verify_token
        self.graph_version = graph_version.strip("/") or "v20.0"
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    def send_message(self, phone: str, text: str) -> dict[str, Any]:
        if not self.configured:
            raise WhatsAppProviderError("Meta WhatsApp provider is not configured")

        url = f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise WhatsAppProviderError(f"Meta send failed: HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise WhatsAppProviderError(f"Meta unavailable: {exc.reason}") from exc

        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise WhatsAppProviderError("Meta returned invalid JSON") from exc
        return {"ok": True, "provider": self.name, "response": data}

    def parse_webhook(self, payload: dict[str, Any]) -> IncomingMessage | None:
        try:
            entry = payload.get("entry", [])[0]
            change = entry.get("changes", [])[0]
            value = change.get("value", {})
            message = value.get("messages", [])[0]
        except (AttributeError, IndexError, TypeError):
            return None

        if message.get("type") != "text":
            return None

        phone = str(message.get("from") or "").strip()
        text = str((message.get("text") or {}).get("body") or "").strip()
        if not phone or not text:
            return None

        name = None
        contacts = value.get("contacts") or []
        if contacts and isinstance(contacts[0], dict):
            profile = contacts[0].get("profile") or {}
            name = profile.get("name")

        return IncomingMessage(
            phone=phone,
            text=text,
            name=name,
            provider_message_id=message.get("id"),
            raw=payload,
        )

    def verify_webhook(self, request_or_query: Any) -> str | None:
        mode = query_value(request_or_query, "hub.mode")
        token = query_value(request_or_query, "hub.verify_token")
        challenge = query_value(request_or_query, "hub.challenge")
        if mode == "subscribe" and token == self.verify_token and challenge:
            return challenge
        return None

