"""Local W2 simulation without WhatsApp, FastAPI, or real CRM credentials."""

from __future__ import annotations

import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.seller_agent import ClubCommerceSellerAgent
from agent.tools import CRMSalesTools


class FakeCRMClient:
    def __init__(self) -> None:
        self.lead = {
            "id": "lead_test_1",
            "name": "Adrian Test",
            "phone": "17865550100",
            "stage": "nuevo",
        }
        self.followups: list[dict[str, Any]] = []
        self.activities: list[dict[str, Any]] = []
        self.handoffs: list[dict[str, Any]] = []

    def lookup_lead(self, phone: str | None = None, email: str | None = None) -> dict[str, Any]:
        return {"ok": True, "found": True, "lead": self.lead}

    def upsert_lead(self, lead: dict[str, Any]) -> dict[str, Any]:
        self.lead.update({k: v for k, v in lead.items() if v not in (None, "")})
        return {"ok": True, "created": False, "lead": self.lead}

    def create_followup(
        self,
        lead_id: str,
        scheduled_at: str,
        note: str,
        followup_type: str = "whatsapp",
        status: str = "pending",
    ) -> dict[str, Any]:
        item = {
            "leadId": lead_id,
            "nextFollowUpAt": scheduled_at,
            "followUpNote": note,
            "followUpType": followup_type,
            "followUpStatus": status,
        }
        self.followups.append(item)
        return {"ok": True, "followUp": item}

    def log_activity(
        self,
        activity_type: str,
        message: str,
        lead_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = {"type": activity_type, "message": message, "leadId": lead_id, "meta": meta or {}}
        self.activities.append(item)
        return {"ok": True, "activity": item}

    def request_human_handoff(
        self,
        lead_id: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        reason: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        item = {"leadId": lead_id, "phone": phone, "reason": reason, "note": note}
        self.handoffs.append(item)
        return {"ok": True, "handoff": item}

    def get_products(self) -> dict[str, Any]:
        return {
            "ok": True,
            "products": [
                {"name": "100X Academy", "price": 1297},
                {"name": "100X PRO PLAN", "price": 2497},
                {"name": "100X ELITE PLAN", "price": 3497},
            ],
        }


def main() -> None:
    fake = FakeCRMClient()
    agent = ClubCommerceSellerAgent(CRMSalesTools(fake))

    pricing = agent.handle_message("+1 (786) 555-0100", "Cuanto cuesta el programa?", "Adrian Test")
    assert pricing.intent == "pricing"
    assert "100X Academy" in pricing.message
    assert fake.followups, "pricing flow should create a follow-up"

    handoff = agent.handle_message("+1 (786) 555-0100", "Quiero comprar, pasame el link", "Adrian Test")
    assert handoff.handoff is True
    assert fake.handoffs, "strong intent should request human handoff"
    assert fake.activities, "agent should log CRM activity"

    print("W2 local simulation OK")
    print(f"Pricing reply: {pricing.message.splitlines()[0]}")
    print(f"Handoff reply: {handoff.message}")


if __name__ == "__main__":
    main()

