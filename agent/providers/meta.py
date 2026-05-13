"""Meta WhatsApp Cloud API provider foundation."""

from __future__ import annotations

import json
import re
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

    def _send_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise WhatsAppProviderError("Meta WhatsApp provider is not configured")

        url = f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}/messages"
        return self._post_json(url, payload)

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            **payload,
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
            raise self._provider_error_from_http(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise WhatsAppProviderError(
                "Meta unavailable",
                provider_message=f"Meta unavailable: {exc.reason}",
                provider_details=str(exc.reason),
            ) from exc

        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise WhatsAppProviderError("Meta returned invalid JSON", provider_details=raw[:500]) from exc
        return {"ok": True, "provider": self.name, "response": data}

    def _provider_error_from_http(self, status: int, detail: str) -> WhatsAppProviderError:
        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(detail or "{}")
        except json.JSONDecodeError:
            parsed = {}
        error = parsed.get("error") if isinstance(parsed, dict) else {}
        error = error if isinstance(error, dict) else {}
        error_data = error.get("error_data") if isinstance(error.get("error_data"), dict) else {}
        details = self._safe_error_text(str(error_data.get("details") or error.get("error_user_msg") or detail))
        message = self._safe_error_text(str(error.get("message") or f"Meta send failed with HTTP {status}"))
        return WhatsAppProviderError(
            "Meta send failed",
            provider_status=status,
            provider_code=error.get("code"),
            provider_subcode=error.get("error_subcode"),
            provider_message=message,
            provider_details=str(details or "")[:1000],
            fbtrace_id=str(error.get("fbtrace_id") or ""),
        )

    def _safe_error_text(self, value: str) -> str:
        text = value.replace(self.access_token, "[redacted]") if self.access_token else value
        if self.phone_number_id:
            text = text.replace(self.phone_number_id, "[phone-number-id]")
        return re.sub(r"\+?\d[\d\s().-]{6,}\d", self._mask_number_match, text)

    @staticmethod
    def _mask_number_match(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return f"***{digits[-4:]}"

    def build_text_payload(self, phone: str, text: str) -> dict[str, Any]:
        return {
            "recipient_type": "individual",
            "to": phone,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }

    def build_template_payload(
        self,
        phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "recipient_type": "individual",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components
        return payload

    def send_message(self, phone: str, text: str) -> dict[str, Any]:
        return self._send_payload(self.build_text_payload(phone, text))

    def send_template(
        self,
        phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self._send_payload(self.build_template_payload(phone, template_name, language_code, components))

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
