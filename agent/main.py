"""FastAPI entrypoint for the Club Commerce WhatsApp Agent.

W2 keeps WhatsApp mocked. Real Meta/Twilio adapters can call the same agent
service once provider credentials are configured in W3/W4.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import load_settings
from .crm_client import CRMClient, CRMClientError
from .seller_agent import ClubCommerceSellerAgent
from .tools import CRMSalesTools


settings = load_settings()
crm_client = CRMClient(settings.crm_api_url, settings.crm_api_key)
sales_tools = CRMSalesTools(crm_client)
seller_agent = ClubCommerceSellerAgent(sales_tools)

app = FastAPI(title="Club Commerce WhatsApp Sales Agent", version="0.2.0")


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
        "crmConfigured": settings.crm_ready,
    }


@app.post("/simulate")
def simulate(payload: SimulateMessage) -> dict[str, Any]:
    try:
        reply = seller_agent.handle_message(
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

