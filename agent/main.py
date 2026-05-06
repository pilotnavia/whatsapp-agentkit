"""FastAPI entrypoint for the Club Commerce WhatsApp Agent.

W2 keeps WhatsApp mocked. Real Meta/Twilio adapters can call the same agent
service once provider credentials are configured in W3/W4.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import PlainTextResponse

from .anthropic_client import AnthropicClient
from .brain import ClaudeSalesBrain
from .config import load_settings
from .crm_client import CRMClient, CRMClientError
from .memory import ConversationMemory
from .providers import WhatsAppProviderError, build_provider
from .tools import CRMSalesTools


settings = load_settings()
crm_client = CRMClient(settings.crm_api_url, settings.crm_api_key)
sales_tools = CRMSalesTools(crm_client)
memory = ConversationMemory(settings.memory_path)
anthropic_client = AnthropicClient(settings.anthropic_api_key, settings.anthropic_model)
seller_brain = ClaudeSalesBrain(sales_tools, memory, anthropic_client)
whatsapp_provider = build_provider(settings)

app = FastAPI(title="Club Commerce WhatsApp Sales Agent", version="0.4.0")


class SimulateMessage(BaseModel):
    phone: str = Field(..., min_length=5)
    message: str = Field(..., min_length=1)
    name: str | None = None
    email: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "club-commerce-whatsapp-agent",
        "provider": settings.whatsapp_provider,
        "providerReady": settings.whatsapp_ready,
        "crmConfigured": settings.crm_ready,
        "claudeConfigured": anthropic_client.ready,
        "model": settings.anthropic_model if anthropic_client.ready else "fallback-local",
    }


@app.post("/simulate")
def simulate(payload: SimulateMessage) -> dict[str, Any]:
    try:
        reply = seller_brain.handle_message(
            phone=payload.phone,
            message=payload.message,
            name=payload.name,
            email=payload.email,
        )
    except CRMClientError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc), "crmStatus": exc.status}) from exc

    return {
        "ok": True,
        "reply": reply.message,
        "intent": reply.intent,
        "handoff": reply.handoff,
        "lead": reply.lead,
    }


@app.post("/webhook/mock")
def webhook_mock(payload: SimulateMessage) -> dict[str, Any]:
    """Provider-neutral mock webhook for local tests."""
    return simulate(payload)


@app.get("/webhook")
def verify_webhook(request: Request) -> PlainTextResponse:
    challenge = whatsapp_provider.verify_webhook(request)
    if not challenge:
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    return PlainTextResponse(challenge)


@app.post("/webhook")
async def receive_webhook(request: Request) -> dict[str, Any]:
    payload = await request.json()
    inbound = whatsapp_provider.parse_webhook(payload)
    if not inbound:
        return {"ok": True, "ignored": True}

    try:
        reply = seller_brain.handle_message(
            phone=inbound.phone,
            message=inbound.text,
            name=inbound.name,
            email=inbound.email,
        )
        send_result = whatsapp_provider.send_message(inbound.phone, reply.message)
    except CRMClientError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc), "crmStatus": exc.status}) from exc
    except WhatsAppProviderError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc

    return {
        "ok": True,
        "provider": whatsapp_provider.name,
        "intent": reply.intent,
        "handoff": reply.handoff,
        "leadId": (reply.lead or {}).get("id"),
        "sent": send_result.get("ok", False),
    }
