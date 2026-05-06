"""Local W2/W3 simulation without WhatsApp, FastAPI, or real CRM credentials."""

from __future__ import annotations

import pathlib
import sys
import tempfile
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.brain import ClaudeSalesBrain
from agent.memory import ConversationMemory
from agent.providers import MetaWhatsAppProvider, MockWhatsAppProvider
from agent.security import mask_phone, sign_meta_payload, verify_meta_signature
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


class FakeAnthropic:
    ready = True

    def complete(self, system: str, messages: list[dict[str, str]], max_tokens: int = 900) -> str:
        last = messages[-1]["content"].casefold()
        if "comprar" in last or "link" in last:
            return (
                '{"reply":"Perfecto, te conecto con un closer del equipo para avanzar con el pago.",'
                '"intent":"ready_for_handoff","handoff":true,"needsFollowUp":false,'
                '"followUpNote":"Handoff por intencion fuerte","followUpMinutes":15,"stage":"interesado"}'
            )
        if "precio" in last or "cuanto" in last:
            assert "100X Academy" in system
            return (
                '{"reply":"Tenemos 100X Academy, PRO y ELITE. Cual quieres revisar primero?",'
                '"intent":"pricing","handoff":false,"needsFollowUp":true,'
                '"followUpNote":"Enviar detalle de planes","followUpMinutes":180,"stage":"interesado"}'
            )
        if "caro" in last:
            return (
                '{"reply":"Te entiendo. Buscas empezar con lo mas accesible o quieres avanzar mas rapido?",'
                '"intent":"price_objection","handoff":false,"needsFollowUp":true,'
                '"followUpNote":"Objecion de precio","followUpMinutes":1440,"stage":"conversacion"}'
            )
        return (
            '{"reply":"Claro, te ayudo. Ya tienes tienda online o estas empezando desde cero?",'
            '"intent":"discovery","handoff":false,"needsFollowUp":true,'
            '"followUpNote":"Calificar lead nuevo","followUpMinutes":1440,"stage":"conversacion"}'
        )


def test_w2_fallback_agent() -> None:
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


def test_w3_claude_brain() -> None:
    fake = FakeCRMClient()
    tools = CRMSalesTools(fake)
    with tempfile.TemporaryDirectory() as temp_dir:
        memory = ConversationMemory(str(pathlib.Path(temp_dir) / "memory.json"))
        brain = ClaudeSalesBrain(tools, memory, FakeAnthropic())

        first = brain.handle_message("+1 (786) 555-0100", "Hola, quiero info", "Adrian Test")
        assert first.intent == "discovery"
        assert "tienda" in first.message

        pricing = brain.handle_message("+1 (786) 555-0100", "Que precio tienen?", "Adrian Test")
        assert pricing.intent == "pricing"
        assert "100X" in pricing.message
        assert fake.followups, "pricing should create follow-up"

        objection = brain.handle_message("+1 (786) 555-0100", "Se me hace caro", "Adrian Test")
        assert objection.intent == "price_objection"

        handoff = brain.handle_message("+1 (786) 555-0100", "Quiero comprar, pasame el link", "Adrian Test")
        assert handoff.handoff is True
        assert fake.handoffs, "strong intent should request human handoff"
        assert len(memory.load("+1 (786) 555-0100")) >= 6

    print("W3 Claude brain simulation OK")
    print(f"Brain handoff reply: {handoff.message}")


def test_w4_mock_provider() -> None:
    provider = MockWhatsAppProvider(verify_token="verify-me")
    challenge = provider.verify_webhook(
        {
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "challenge-ok",
        }
    )
    assert challenge == "challenge-ok"

    incoming = provider.parse_webhook(
        {
            "phone": "+17865550100",
            "message": "Hola desde mock",
            "name": "Adrian Test",
            "id": "mock_msg_1",
        }
    )
    assert incoming is not None
    assert incoming.phone == "+17865550100"
    assert incoming.text == "Hola desde mock"

    sent = provider.send_message("+17865550100", "Respuesta mock")
    assert sent["ok"] is True
    assert provider.sent_messages[-1]["text"] == "Respuesta mock"

    print("W4 mock provider simulation OK")


def test_w4_meta_provider_parse() -> None:
    provider = MetaWhatsAppProvider(
        access_token="token-not-used",
        phone_number_id="123456",
        verify_token="meta-verify",
    )
    challenge = provider.verify_webhook(
        {
            "hub.mode": "subscribe",
            "hub.verify_token": "meta-verify",
            "hub.challenge": "meta-challenge",
        }
    )
    assert challenge == "meta-challenge"

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"profile": {"name": "Lead Meta"}}],
                            "messages": [
                                {
                                    "from": "17865550100",
                                    "id": "wamid.test",
                                    "type": "text",
                                    "text": {"body": "Cuanto cuesta?"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    incoming = provider.parse_webhook(payload)
    assert incoming is not None
    assert incoming.phone == "17865550100"
    assert incoming.name == "Lead Meta"
    assert incoming.text == "Cuanto cuesta?"

    ignored = provider.parse_webhook(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "17865550100",
                                        "id": "wamid.image",
                                        "type": "image",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert ignored is None

    print("W4 Meta provider parse simulation OK")


def test_w5_meta_signature_security() -> None:
    body = b'{"entry":[{"changes":[{"value":{"messages":[]}}]}]}'
    secret = "app-secret-for-test"
    signature = sign_meta_payload(body, secret)
    assert verify_meta_signature(body, signature, secret) is True
    assert verify_meta_signature(body, "sha256=bad", secret) is False
    assert verify_meta_signature(body, signature, "wrong-secret") is False
    assert verify_meta_signature(body, None, secret) is False
    assert verify_meta_signature(body, signature, "") is False
    assert mask_phone("+1 (786) 555-0100") == "***0100"

    print("W5 Meta signature security simulation OK")


def main() -> None:
    test_w2_fallback_agent()
    test_w3_claude_brain()
    test_w4_mock_provider()
    test_w4_meta_provider_parse()
    test_w5_meta_signature_security()


if __name__ == "__main__":
    main()
