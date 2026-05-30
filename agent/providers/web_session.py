"""Experimental WhatsApp Web sidecar provider.

This transport delegates WhatsApp Web session handling to the Node sidecar.
It is intentionally conservative and marked experimental because it relies on
an unofficial WhatsApp Web automation path.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .base import IncomingMessage, WhatsAppProviderError


class WebSessionWhatsAppProvider:
    name = "web_session"

    def __init__(self, bridge_url: str, api_key: str, default_session_id: str, timeout_seconds: int = 15):
        self.bridge_url = (bridge_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.default_session_id = default_session_id or ""
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.bridge_url and self.api_key and self.default_session_id)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.bridge_url:
            raise WhatsAppProviderError("WEB_SESSION_BRIDGE_URL is not configured", provider_message="Bridge URL missing")
        if not self.api_key:
            raise WhatsAppProviderError("WEB_SESSION_BRIDGE_API_KEY is not configured", provider_message="Bridge API key missing")
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.bridge_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8") or "{}"
                body = json.loads(raw)
                return body if isinstance(body, dict) else {"ok": False, "error": "Invalid bridge response"}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            try:
                body = json.loads(raw or "{}")
            except json.JSONDecodeError:
                body = {}
            message = str(body.get("error") or exc.reason or "Bridge request failed")
            raise WhatsAppProviderError(
                "WhatsApp Web bridge request failed",
                provider_status=exc.code,
                provider_code="web_session_bridge_error",
                provider_message=message,
                provider_details=str(body.get("hint") or body.get("warning") or ""),
            ) from exc
        except Exception as exc:
            raise WhatsAppProviderError(
                "WhatsApp Web bridge unavailable",
                provider_code="web_session_unreachable",
                provider_message=str(exc),
            ) from exc

    def health(self) -> dict[str, Any]:
        try:
            request = urllib.request.Request(f"{self.bridge_url}/health", headers={"Accept": "application/json"}, method="GET")
            with urllib.request.urlopen(request, timeout=min(self.timeout_seconds, 5)) as response:
                raw = response.read().decode("utf-8") or "{}"
                body = json.loads(raw)
                return body if isinstance(body, dict) else {"ok": False}
        except Exception as exc:
            return {"ok": False, "reachable": False, "error": str(exc)}

    def readiness(self) -> dict[str, Any]:
        if not self.default_session_id:
            return {"ok": False, "error": "WEB_SESSION_DEFAULT_SESSION_ID missing"}
        return self._request("GET", f"/sessions/{self.default_session_id}/readiness")

    def _session_id(self, metadata: dict[str, Any] | None = None) -> str:
        if isinstance(metadata, dict) and metadata.get("sessionId"):
            return str(metadata.get("sessionId") or "").strip()
        return self.default_session_id

    def send_message(self, phone: str, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        session_id = self._session_id(metadata)
        if not session_id:
            raise WhatsAppProviderError("WEB_SESSION_DEFAULT_SESSION_ID is not configured", provider_message="Bridge session missing")
        return self._request("POST", f"/sessions/{session_id}/send-message", {"phone": phone, "body": text, "metadata": metadata or {}})

    def send_template(
        self,
        phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: list[dict[str, Any]] | None = None,
        *,
        rendered_body: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # WhatsApp Web cannot send official templates. The CRM must provide a
        # rendered preview; the sidecar sends that text through an active session.
        body = (rendered_body or "").strip()
        if not body:
            body = f"Template {template_name} ({language_code})"
        result = self.send_message(phone, body, metadata={**(metadata or {}), "templateName": template_name, "languageCode": language_code})
        result["templateName"] = template_name
        result["languageCode"] = language_code
        result["warning"] = "web_session sends rendered template text, not official Meta templates."
        return result

    def parse_webhook(self, payload: dict[str, Any]) -> IncomingMessage | None:
        if str(payload.get("provider") or "").lower() not in {"web_session", "whatsapp_web", ""}:
            return None
        phone = str(payload.get("from") or payload.get("phone") or "").strip()
        text = str(payload.get("body") or payload.get("message") or payload.get("text") or "").strip()
        if not phone or not text:
            return None
        return IncomingMessage(
            phone=phone,
            text=text,
            name=payload.get("name"),
            email=payload.get("email"),
            provider_message_id=str(payload.get("messageId") or payload.get("providerMessageId") or ""),
            raw=payload,
        )

    def verify_webhook(self, request_or_query: Any) -> str | None:
        return None
