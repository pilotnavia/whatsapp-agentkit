"""Agent tools backed by the Club Commerce CRM Bridge."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol


class CRMClientProtocol(Protocol):
    def lookup_lead(self, phone: str | None = None, email: str | None = None) -> dict[str, Any]: ...
    def upsert_lead(self, lead: dict[str, Any]) -> dict[str, Any]: ...
    def create_followup(
        self,
        lead_id: str,
        scheduled_at: str,
        note: str,
        followup_type: str = "whatsapp",
        status: str = "pending",
    ) -> dict[str, Any]: ...
    def log_activity(
        self,
        activity_type: str,
        message: str,
        lead_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    def request_human_handoff(
        self,
        lead_id: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        reason: str = "",
        note: str = "",
    ) -> dict[str, Any]: ...
    def get_products(self) -> dict[str, Any]: ...


def normalize_phone(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\D+", "", value)


def utc_in(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


class CRMSalesTools:
    def __init__(self, crm: CRMClientProtocol):
        self.crm = crm

    def lookup_lead(self, phone: str | None = None, email: str | None = None) -> dict[str, Any]:
        return self.crm.lookup_lead(phone=normalize_phone(phone), email=email)

    def upsert_lead(
        self,
        phone: str,
        message: str,
        name: str | None = None,
        email: str | None = None,
        intent: str | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        clean_phone = normalize_phone(phone)
        intake_answer = {
            "label": "Mensaje inicial WhatsApp",
            "value": message,
            "key": "whatsapp_initial_message",
        }
        if intent:
            intake_answer_intent = {
                "label": "Intencion detectada",
                "value": intent,
                "key": "agent_detected_intent",
            }
        else:
            intake_answer_intent = None
        payload = {
            "phone": clean_phone,
            "email": email,
            "name": name,
            "source": "WhatsApp",
            "campaign": "WhatsApp AI Agent",
            "stage": stage,
            "notes": f"WhatsApp AI: {message}".strip(),
            "intake": {
                "summary": f"WhatsApp: {message}".strip()[:1000],
                "answers": [item for item in (intake_answer, intake_answer_intent) if item],
                "sourcePayload": {
                    "platform": "whatsapp",
                    "phone": clean_phone,
                },
            },
            "meta": {
                "intent": intent,
                "lastInboundMessage": message,
                "whatsappPhone": clean_phone,
                "channel": "whatsapp",
            },
        }
        return self.crm.upsert_lead(payload)

    def create_followup(
        self,
        lead_id: str,
        note: str,
        minutes_from_now: int = 1440,
        followup_type: str = "whatsapp",
    ) -> dict[str, Any]:
        return self.crm.create_followup(
            lead_id=lead_id,
            scheduled_at=utc_in(minutes_from_now),
            note=note,
            followup_type=followup_type,
            status="pending",
        )

    def log_activity(
        self,
        message: str,
        lead_id: str | None = None,
        activity_type: str = "whatsapp_agent",
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.crm.log_activity(activity_type, message, lead_id=lead_id, meta=meta or {})

    def request_human_handoff(
        self,
        lead_id: str | None,
        phone: str,
        reason: str,
        note: str,
        email: str | None = None,
    ) -> dict[str, Any]:
        return self.crm.request_human_handoff(
            lead_id=lead_id,
            phone=normalize_phone(phone),
            email=email,
            reason=reason,
            note=note,
        )

    def get_products(self) -> list[dict[str, Any]]:
        response = self.crm.get_products()
        products = response.get("products", response if isinstance(response, list) else [])
        return products if isinstance(products, list) else []
