"""Mock WhatsApp provider for local tests and development."""

from __future__ import annotations

from typing import Any

from .base import IncomingMessage, query_value


class MockWhatsAppProvider:
    name = "mock"

    def __init__(self, verify_token: str = "mock-verify"):
        self.verify_token = verify_token
        self.sent_messages: list[dict[str, str]] = []
        self.sent_templates: list[dict[str, Any]] = []

    def send_message(self, phone: str, text: str) -> dict[str, Any]:
        item = {"phone": phone, "text": text}
        self.sent_messages.append(item)
        return {"ok": True, "provider": self.name, "message": item}

    def send_template(
        self,
        phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        item = {
            "phone": phone,
            "templateName": template_name,
            "languageCode": language_code,
            "components": components or [],
        }
        self.sent_templates.append(item)
        return {"ok": True, "provider": self.name, "template": item}

    def parse_webhook(self, payload: dict[str, Any]) -> IncomingMessage | None:
        phone = str(payload.get("phone") or payload.get("from") or "").strip()
        text = str(payload.get("message") or payload.get("text") or payload.get("body") or "").strip()
        if not phone or not text:
            return None
        return IncomingMessage(
            phone=phone,
            text=text,
            name=payload.get("name"),
            email=payload.get("email"),
            provider_message_id=payload.get("id"),
            raw=payload,
        )

    def verify_webhook(self, request_or_query: Any) -> str | None:
        mode = query_value(request_or_query, "hub.mode")
        token = query_value(request_or_query, "hub.verify_token")
        challenge = query_value(request_or_query, "hub.challenge")
        if mode == "subscribe" and token == self.verify_token and challenge:
            return challenge
        return None
