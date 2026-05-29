"""Local W2/W3 simulation without WhatsApp, FastAPI, or real CRM credentials."""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import tempfile
from types import SimpleNamespace
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.api_auth import agent_api_key_valid
from agent.brain import ClaudeSalesBrain
from agent.memory import ConversationMemory
from agent.providers import MetaWhatsAppProvider, MockWhatsAppProvider
from agent.providers.base import IncomingMessage, WhatsAppProviderError, provider_error_hint
from agent.security import mask_phone, sign_meta_payload, verify_meta_signature
from agent.seller_agent import ClubCommerceSellerAgent
from agent.tools import CRMSalesTools
from agent.webhook_handler import WebhookHTTPError, process_webhook_body, reset_seen_messages_for_tests


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
        self.qualifications: list[dict[str, Any]] = []

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
        handoff_trigger: str = "",
        handoff_summary: str = "",
        recommended_next_step: str = "",
        confidence: str = "medium",
    ) -> dict[str, Any]:
        item = {
            "leadId": lead_id,
            "phone": phone,
            "reason": reason,
            "note": note,
            "handoffTrigger": handoff_trigger,
            "handoffSummary": handoff_summary,
            "recommendedNextStep": recommended_next_step,
            "confidence": confidence,
        }
        self.handoffs.append(item)
        return {"ok": True, "handoff": item}

    def submit_qualification(self, lead_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        item = {"leadId": lead_id, **payload}
        self.qualifications.append(item)
        return {"ok": True, "qualification": item}

    def get_products(self) -> dict[str, Any]:
        return {
            "ok": True,
            "products": [
                {"name": "100X Academy", "price": 1297},
                {"name": "100X PRO PLAN", "price": 2497},
                {"name": "100X ELITE PLAN", "price": 3497},
            ],
        }

    def get_agent_tools(self) -> dict[str, Any]:
        return {
            "ok": True,
            "tools": [
                {"key": "propose_sales_action", "status": "enabled"},
                {"key": "request_handoff", "status": "enabled"},
                {"key": "create_followup_task", "status": "enabled"},
                {"key": "enqueue_template", "status": "enabled"},
                {"key": "enroll_sequence", "status": "enabled"},
                {"key": "update_lead_safe_fields", "status": "enabled"},
            ],
        }


class FakeAnthropic:
    ready = True

    def complete(self, system: str, messages: list[dict[str, str]], max_tokens: int = 900) -> str:
        assert "SIEMPRE en espanol" in system
        last = messages[-1]["content"].casefold()
        if "shopify" in last:
            assert "Conocimiento base permitido" in system
            assert "Shopify" in system
            return (
                '{"reply":"Shopify ayuda, pero primero hay que validar oferta, producto y pagina. Ya tienes tienda creada?",'
                '"intent":"shopify_question","handoff":false,"needsFollowUp":true,'
                '"followUpNote":"Diagnosticar tienda Shopify","followUpMinutes":1440,"stage":"conversacion"}'
            )
        if "comprar" in last or "link" in last:
            return (
                '{"reply":"Perfecto, te conecto con un asesor del equipo para avanzar con el pago.",'
                '"intent":"ready_for_handoff","handoff":true,"needsFollowUp":false,'
                '"followUpNote":"Handoff por intencion fuerte","followUpMinutes":15,"stage":"interesado",'
                '"handoffReason":"Lead pidio link de pago","handoffTrigger":"payment",'
                '"handoffSummary":"Quiere comprar y pidio el link.","recommendedNextStep":"Enviar opciones de pago y cerrar.",'
                '"confidence":"high"}'
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


class FakeAnthropicEnglish:
    ready = True

    def complete(self, system: str, messages: list[dict[str, str]], max_tokens: int = 900) -> str:
        assert "SIEMPRE en espanol" in system
        return (
            '{"reply":"Sure, I can help you. Do you already have an online store?",'
            '"intent":"shopify_question","handoff":false,"needsFollowUp":true,'
            '"followUpNote":"Bad English reply","followUpMinutes":1440,"stage":"conversacion"}'
        )


class FakeMetaProviderForWebhook:
    name = "meta"

    def __init__(self, fail_send: bool = False) -> None:
        self.fail_send = fail_send
        self.sent: list[dict[str, str]] = []

    def parse_webhook(self, payload: dict[str, Any]) -> IncomingMessage | None:
        try:
            value = payload["entry"][0]["changes"][0]["value"]
            message = value["messages"][0]
        except (KeyError, IndexError, TypeError):
            return None
        if message.get("type") != "text":
            return None
        text = (message.get("text") or {}).get("body", "")
        if not str(text).strip():
            return None
        return IncomingMessage(
            phone=message.get("from", ""),
            text=text,
            name="Webhook Test",
            provider_message_id=message.get("id"),
            raw=payload,
        )

    def send_message(self, phone: str, text: str) -> dict[str, Any]:
        if self.fail_send:
            raise WhatsAppProviderError("send failed in test")
        self.sent.append({"phone": phone, "text": text})
        return {"ok": True}


class FakeBrainForWebhook:
    def __init__(self, tools: CRMSalesTools | None = None) -> None:
        self.tools = tools
        self.calls = 0

    def handle_message(
        self,
        phone: str,
        message: str,
        name: str | None = None,
        email: str | None = None,
    ) -> Any:
        self.calls += 1
        return SimpleNamespace(
            message="Respuesta controlada",
            intent="discovery",
            handoff=False,
            lead={"id": "lead_webhook_test"},
        )


def meta_settings(secret: str = "app-secret-for-test") -> SimpleNamespace:
    return SimpleNamespace(whatsapp_provider="meta", meta_app_secret=secret)


def sample_meta_payload(with_messages: bool = True, message_id: str = "wamid.test", message_type: str = "text", body: str = "Hola, quiero informacion") -> dict[str, Any]:
    value: dict[str, Any] = {}
    if with_messages:
        value["contacts"] = [{"profile": {"name": "Lead Meta"}}]
        message = {
            "from": "17865550100",
            "id": message_id,
            "type": message_type,
        }
        if message_type == "text":
            message["text"] = {"body": body}
        value["messages"] = [message]
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": value,
                    }
                ]
            }
        ],
    }


def assert_spanish_customer_reply(message: str) -> None:
    lowered = message.casefold()
    forbidden = (
        "how can i",
        "i can help",
        "what is your",
        "do you have",
        "let me",
        "sure,",
        "would you",
    )
    assert not any(marker in lowered for marker in forbidden), message
    assert any(
        marker in lowered
        for marker in (
            "tienda",
            "producto",
            "presupuesto",
            "equipo",
            "asesor",
            "ayudo",
            "programa",
            "ofertas",
            "claro",
            "perfecto",
        )
    ), message
    assert len(message.splitlines()) <= 5, message


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
    assert fake.handoffs[-1]["handoffTrigger"] == "high_intent"
    assert fake.handoffs[-1]["recommendedNextStep"]
    assert fake.qualifications, "strong intent should submit AI qualification"
    assert fake.qualifications[-1]["status"] in {"qualified", "needs_human"}
    assert fake.activities, "agent should log CRM activity"

    print("W2 local simulation OK")
    print(f"Pricing reply: {pricing.message.splitlines()[0]}")
    print(f"Handoff reply: {handoff.message}")


def test_w12_ecommerce_playbook_fallback() -> None:
    scenarios = [
        ("Que necesito para empezar en ecommerce?", "ecommerce_general", "validar"),
        ("No se Shopify y no tengo ventas", "shopify_question", "Shopify"),
        ("Probe Meta Ads y perdi dinero", "meta_ads_lost_money", "presupuesto"),
        ("Quiero hacer dropshipping desde cero", "dropshipping_question", "Dropshipping"),
        ("Quiero importar desde China con proveedores", "china_import_question", "China"),
        ("No tengo producto ganador todavia", "product_validation", "producto"),
        ("Tengo presupuesto de $1000 para iniciar", "budget_capture", "presupuesto"),
        ("Mandame info del programa", "info_request", "asesor"),
        ("Quiero hablar con alguien humano", "ready_for_handoff", "equipo"),
    ]

    for message, expected_intent, expected_text in scenarios:
        fake = FakeCRMClient()
        reply = ClubCommerceSellerAgent(CRMSalesTools(fake)).handle_message(
            "+1 (786) 555-0100",
            message,
            "Lead Ecommerce",
        )
        assert reply.intent == expected_intent, message
        assert expected_text.casefold() in reply.message.casefold(), message
        assert fake.lead.get("intake", {}).get("answers"), message
        assert fake.activities, message

    budget_fake = FakeCRMClient()
    ClubCommerceSellerAgent(CRMSalesTools(budget_fake)).handle_message(
        "+1 (786) 555-0100",
        "Tengo presupuesto de $1000 para iniciar",
        "Lead Budget",
    )
    answers = budget_fake.lead.get("intake", {}).get("answers", [])
    assert any(item.get("key") == "budget" and "1000" in item.get("value", "") for item in answers)
    assert any(item.get("key") == "recommended_product" for item in answers)

    ads_fake = FakeCRMClient()
    ClubCommerceSellerAgent(CRMSalesTools(ads_fake)).handle_message(
        "+1 (786) 555-0100",
        "Probe Meta Ads y perdi dinero con presupuesto de $500",
        "Lead Ads",
    )
    assert any(item["type"] == "agent_insight" for item in ads_fake.activities)
    assert any(
        item.get("key") == "main_objection" and "ads" in item.get("value", "").casefold()
        for item in ads_fake.lead.get("intake", {}).get("answers", [])
    )

    print("W12 ecommerce playbook fallback OK")


def test_w18a_spanish_only_fallback_agent() -> None:
    fake = FakeCRMClient()
    agent = ClubCommerceSellerAgent(CRMSalesTools(fake))

    english_shopify = agent.handle_message(
        "+1 (786) 555-0100",
        "Hi, I want to start an online store with Shopify",
        "English Lead",
    )
    assert english_shopify.intent == "shopify_question"
    assert_spanish_customer_reply(english_shopify.message)

    english_price = agent.handle_message(
        "+1 (786) 555-0100",
        "How much is the program?",
        "English Lead",
    )
    assert english_price.intent == "pricing"
    assert "100X Academy" in english_price.message
    assert_spanish_customer_reply(english_price.message)

    english_handoff = agent.handle_message(
        "+1 (786) 555-0100",
        "I want to talk to a human",
        "English Lead",
    )
    assert english_handoff.handoff is True
    assert english_handoff.intent == "ready_for_handoff"
    assert_spanish_customer_reply(english_handoff.message)

    english_beginner = agent.handle_message(
        "+1 (786) 555-0100",
        "I am starting from scratch with dropshipping",
        "English Lead",
    )
    assert english_beginner.intent in {"dropshipping_question", "experience_question"}
    assert_spanish_customer_reply(english_beginner.message)

    print("W18A Spanish-only fallback responses OK")


def test_w3_claude_brain() -> None:
    fake = FakeCRMClient()
    tools = CRMSalesTools(fake)
    with tempfile.TemporaryDirectory() as temp_dir:
        memory = ConversationMemory(str(pathlib.Path(temp_dir) / "memory.json"))
        brain = ClaudeSalesBrain(tools, memory, FakeAnthropic())

        first = brain.handle_message("+1 (786) 555-0100", "Hola, quiero info", "Adrian Test")
        assert first.intent == "discovery"
        assert "tienda" in first.message
        assert fake.lead.get("intake", {}).get("answers"), "WhatsApp context should sync into CRM intake"
        assert fake.lead.get("meta", {}).get("whatsappPhone") == "17865550100"

        pricing = brain.handle_message("+1 (786) 555-0100", "Que precio tienen?", "Adrian Test")
        assert pricing.intent == "pricing"
        assert "100X" in pricing.message
        assert fake.followups, "pricing should create follow-up"

        objection = brain.handle_message("+1 (786) 555-0100", "Se me hace caro", "Adrian Test")
        assert objection.intent == "price_objection"

        shopify = brain.handle_message("+1 (786) 555-0100", "No se Shopify", "Adrian Test")
        assert shopify.intent == "shopify_question"
        assert "tienda" in shopify.message.casefold()

        handoff = brain.handle_message("+1 (786) 555-0100", "Quiero comprar, pasame el link", "Adrian Test")
        assert handoff.handoff is True
        assert fake.handoffs, "strong intent should request human handoff"
        assert fake.handoffs[-1]["handoffTrigger"] == "payment"
        assert fake.handoffs[-1]["confidence"] == "high"
        assert fake.qualifications, "Claude strong intent should submit AI qualification"
        assert fake.qualifications[-1]["status"] in {"qualified", "needs_human"}
        assert len(memory.load("+1 (786) 555-0100")) >= 6

    print("W3 Claude brain simulation OK")
    print(f"Brain handoff reply: {handoff.message}")


def test_w18a_claude_english_reply_falls_back_to_spanish() -> None:
    fake = FakeCRMClient()
    tools = CRMSalesTools(fake)
    with tempfile.TemporaryDirectory() as temp_dir:
        memory = ConversationMemory(str(pathlib.Path(temp_dir) / "memory.json"))
        brain = ClaudeSalesBrain(tools, memory, FakeAnthropicEnglish())

        reply = brain.handle_message(
            "+1 (786) 555-0100",
            "Can you help me with Shopify?",
            "English Lead",
        )
        assert reply.intent == "shopify_question"
        assert_spanish_customer_reply(reply.message)
        assert "Sure" not in reply.message

    print("W18A Claude English guardrail fallback OK")


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


def test_w14_template_provider_foundation() -> None:
    mock = MockWhatsAppProvider(verify_token="verify-me")
    mock_result = mock.send_template("+17865550100", "hello_world", "en_US", [])
    assert mock_result["ok"] is True
    assert mock_result["provider"] == "mock"
    assert mock.sent_templates[-1]["templateName"] == "hello_world"

    meta = MetaWhatsAppProvider(
        access_token="token-not-used",
        phone_number_id="123456",
        verify_token="meta-verify",
    )
    payload = meta.build_template_payload(
        "+17865550100",
        "lead_followup_1",
        "es",
        [{"type": "body", "parameters": [{"type": "text", "text": "Adrian"}]}],
    )
    assert payload["to"] == "+17865550100"
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "lead_followup_1"
    assert payload["template"]["language"]["code"] == "es"
    assert payload["template"]["components"][0]["type"] == "body"

    assert agent_api_key_valid(None, "expected-key") is False
    assert agent_api_key_valid("bad-key", "expected-key") is False
    assert agent_api_key_valid("expected-key", "expected-key") is True

    print("W14 template provider foundation OK")


def test_meta_provider_error_serializes_safely() -> None:
    meta = MetaWhatsAppProvider(
        access_token="secret-token-not-for-logs",
        phone_number_id="123456",
        verify_token="meta-verify",
    )
    detail = json.dumps({
        "error": {
            "message": "(#132001) Template name does not exist in the translation",
            "type": "OAuthException",
            "code": 132001,
            "error_subcode": 2494015,
            "error_data": {"details": "template not found for language es"},
            "fbtrace_id": "TRACE123",
        }
    })
    error = meta._provider_error_from_http(400, detail)
    payload = error.safe_payload()
    assert payload["providerStatus"] == 400
    assert payload["providerCode"] == "132001"
    assert payload["providerSubcode"] == "2494015"
    assert "Template name" in payload["providerMessage"]
    assert payload["providerDetails"] == "template not found for language es"
    assert payload["fbtraceId"] == "TRACE123"
    assert "secret-token-not-for-logs" not in json.dumps(payload)

    print("W18G Meta provider safe error serialization OK")


def test_meta_token_error_hint_is_specific() -> None:
    error = WhatsAppProviderError(
        "Meta send failed",
        provider_status=401,
        provider_code=190,
        provider_message="Authentication Error",
    )
    hint = provider_error_hint(error)
    assert "META_ACCESS_TOKEN" in hint
    assert "expirado" in hint

    print("W18H Meta token diagnostic hint OK")


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


def test_webhook_missing_signature_is_401() -> None:
    reset_seen_messages_for_tests()
    body = json.dumps(sample_meta_payload()).encode("utf-8")
    try:
        asyncio.run(
            process_webhook_body(
                body,
                None,
                current_settings=meta_settings(),
                provider=FakeMetaProviderForWebhook(),
                brain=FakeBrainForWebhook(),
            )
        )
    except WebhookHTTPError as exc:
        assert exc.status_code == 401
        assert "signature" in str(exc.detail).casefold()
    else:
        raise AssertionError("missing Meta signature should return HTTP 401")

    print("Webhook missing signature returns 401 OK")


def test_webhook_without_messages_is_ignored() -> None:
    reset_seen_messages_for_tests()
    payload = sample_meta_payload(with_messages=False)
    body = json.dumps(payload).encode("utf-8")
    signature = sign_meta_payload(body, "app-secret-for-test")
    result = asyncio.run(
        process_webhook_body(
            body,
            signature,
            current_settings=meta_settings(),
            provider=FakeMetaProviderForWebhook(),
            brain=FakeBrainForWebhook(),
        )
    )
    assert result == {"ok": True, "ignored": True}

    print("Webhook without messages ignored OK")


def test_webhook_sample_message_never_crashes_on_send_failure() -> None:
    reset_seen_messages_for_tests()
    payload = sample_meta_payload(with_messages=True, message_id="wamid.send.failure")
    body = json.dumps(payload).encode("utf-8")
    signature = sign_meta_payload(body, "app-secret-for-test")
    result = asyncio.run(
        process_webhook_body(
            body,
            signature,
            current_settings=meta_settings(),
            provider=FakeMetaProviderForWebhook(fail_send=True),
            brain=FakeBrainForWebhook(),
        )
    )
    assert result["ok"] is True
    assert result["accepted"] is False
    assert result["error"] == "processing_failed"

    print("Webhook sample message failure returns 200 body OK")


def test_webhook_human_takeover_pauses_auto_reply() -> None:
    reset_seen_messages_for_tests()
    fake = FakeCRMClient()
    fake.lead["whatsapp"] = {
        "mode": "human",
        "humanOwnerId": "user_admin_adrian",
        "humanOwnerName": "Adrian",
    }
    provider = FakeMetaProviderForWebhook()
    brain = FakeBrainForWebhook(CRMSalesTools(fake))
    payload = sample_meta_payload(with_messages=True, message_id="wamid.takeover")
    body = json.dumps(payload).encode("utf-8")
    signature = sign_meta_payload(body, "app-secret-for-test")
    result = asyncio.run(
        process_webhook_body(
            body,
            signature,
            current_settings=meta_settings(),
            provider=provider,
            brain=brain,
        )
    )
    assert result["ok"] is True
    assert result["paused"] is True
    assert result["mode"] == "human"
    assert brain.calls == 0
    assert provider.sent == []
    assert any(item["type"] == "whatsapp_inbound" and item["message"] == "Hola, quiero informacion" for item in fake.activities)
    assert any(item["type"] == "whatsapp_system" for item in fake.activities)

    print("Webhook human takeover pause OK")


def test_w13_duplicate_message_is_ignored() -> None:
    reset_seen_messages_for_tests()
    payload = sample_meta_payload(with_messages=True, message_id="wamid.duplicate")
    body = json.dumps(payload).encode("utf-8")
    signature = sign_meta_payload(body, "app-secret-for-test")
    provider = FakeMetaProviderForWebhook()
    fake = FakeCRMClient()
    brain = FakeBrainForWebhook(CRMSalesTools(fake))
    first = asyncio.run(
        process_webhook_body(
            body,
            signature,
            current_settings=meta_settings(),
            provider=provider,
            brain=brain,
        )
    )
    second = asyncio.run(
        process_webhook_body(
            body,
            signature,
            current_settings=meta_settings(),
            provider=provider,
            brain=brain,
        )
    )
    assert first["ok"] is True
    assert second["ignored"] is True
    assert second["duplicate"] is True
    assert brain.calls == 1
    assert len(provider.sent) == 1
    assert any(
        item["type"] == "whatsapp_outbound_bot"
        and item["message"] == "Respuesta controlada"
        and item["meta"].get("sender") == "bot"
        for item in fake.activities
    )

    print("W13 duplicate message ignored OK")


def test_w13_empty_message_is_ignored() -> None:
    reset_seen_messages_for_tests()
    payload = sample_meta_payload(with_messages=True, message_id="wamid.empty", body="   ")
    body = json.dumps(payload).encode("utf-8")
    signature = sign_meta_payload(body, "app-secret-for-test")
    brain = FakeBrainForWebhook()
    result = asyncio.run(
        process_webhook_body(
            body,
            signature,
            current_settings=meta_settings(),
            provider=FakeMetaProviderForWebhook(),
            brain=brain,
        )
    )
    assert result["ok"] is True
    assert result["ignored"] is True
    assert brain.calls == 0

    print("W13 empty message ignored OK")


def test_w13_unsupported_type_is_ignored() -> None:
    reset_seen_messages_for_tests()
    payload = sample_meta_payload(with_messages=True, message_id="wamid.image", message_type="image")
    body = json.dumps(payload).encode("utf-8")
    signature = sign_meta_payload(body, "app-secret-for-test")
    brain = FakeBrainForWebhook()
    result = asyncio.run(
        process_webhook_body(
            body,
            signature,
            current_settings=meta_settings(),
            provider=FakeMetaProviderForWebhook(),
            brain=brain,
        )
    )
    assert result["ok"] is True
    assert result["ignored"] is True
    assert brain.calls == 0

    print("W13 unsupported message ignored OK")


def test_w13_oversized_message_is_ignored() -> None:
    reset_seen_messages_for_tests()
    payload = sample_meta_payload(with_messages=True, message_id="wamid.long", body="x" * 1601)
    body = json.dumps(payload).encode("utf-8")
    signature = sign_meta_payload(body, "app-secret-for-test")
    brain = FakeBrainForWebhook()
    result = asyncio.run(
        process_webhook_body(
            body,
            signature,
            current_settings=meta_settings(),
            provider=FakeMetaProviderForWebhook(),
            brain=brain,
        )
    )
    assert result["ok"] is True
    assert result["ignored"] is True
    assert result["reason"] == "message_too_long"
    assert brain.calls == 0

    print("W13 oversized message ignored OK")


def main() -> None:
    test_w2_fallback_agent()
    test_w12_ecommerce_playbook_fallback()
    test_w18a_spanish_only_fallback_agent()
    test_w3_claude_brain()
    test_w18a_claude_english_reply_falls_back_to_spanish()
    test_w4_mock_provider()
    test_w4_meta_provider_parse()
    test_w14_template_provider_foundation()
    test_meta_provider_error_serializes_safely()
    test_meta_token_error_hint_is_specific()
    test_w5_meta_signature_security()
    test_webhook_missing_signature_is_401()
    test_webhook_without_messages_is_ignored()
    test_webhook_sample_message_never_crashes_on_send_failure()
    test_webhook_human_takeover_pauses_auto_reply()
    test_w13_duplicate_message_is_ignored()
    test_w13_empty_message_is_ignored()
    test_w13_unsupported_type_is_ignored()
    test_w13_oversized_message_is_ignored()


if __name__ == "__main__":
    main()
