"""Small HTTP client for the Club Commerce CRM Bridge endpoints."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class CRMClientError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class CRMClient:
    def __init__(self, api_url: str, api_key: str, timeout: float = 12):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.api_url or not self.api_key:
            raise CRMClientError("CRM_API_URL and CRM_API_KEY are required")

        url = f"{self.api_url}{path}"
        if query:
            clean_query = {k: v for k, v in query.items() if v not in (None, "")}
            if clean_query:
                url = f"{url}?{urllib.parse.urlencode(clean_query)}"

        body = None
        headers = {
            "Accept": "application/json",
            "x-crm-api-key": self.api_key,
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload_data = json.loads(raw)
            except json.JSONDecodeError:
                payload_data = raw
            raise CRMClientError("CRM request failed", status=exc.code, payload=payload_data) from exc
        except urllib.error.URLError as exc:
            raise CRMClientError(f"CRM unavailable: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise CRMClientError("CRM returned invalid JSON") from exc

    def lookup_lead(self, phone: str | None = None, email: str | None = None) -> dict[str, Any]:
        return self._request("GET", "/api/agent/leads/lookup", query={"phone": phone, "email": email})

    def upsert_lead(self, lead: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/agent/leads/upsert", payload=lead)

    def create_followup(
        self,
        lead_id: str,
        scheduled_at: str,
        note: str,
        followup_type: str = "whatsapp",
        status: str = "pending",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/agent/leads/{urllib.parse.quote(str(lead_id), safe='')}/follow-up",
            payload={
                "nextFollowUpAt": scheduled_at,
                "followUpType": followup_type,
                "followUpNote": note,
                "followUpStatus": status,
            },
        )

    def log_activity(
        self,
        activity_type: str,
        message: str,
        lead_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/agent/activities",
            payload={
                "type": activity_type,
                "message": message,
                "leadId": lead_id,
                "meta": meta or {},
            },
        )

    def request_human_handoff(
        self,
        lead_id: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        reason: str = "Intento fuerte detectado por WhatsApp AI Agent",
        note: str = "",
        handoff_trigger: str = "",
        handoff_summary: str = "",
        recommended_next_step: str = "",
        confidence: str = "medium",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/agent/handoff",
            payload={
                "leadId": lead_id,
                "phone": phone,
                "email": email,
                "reason": reason,
                "note": note,
                "handoffTrigger": handoff_trigger,
                "handoffSummary": handoff_summary,
                "recommendedNextStep": recommended_next_step,
                "confidence": confidence,
            },
        )

    def get_products(self) -> dict[str, Any]:
        return self._request("GET", "/api/agent/products")
