"""FastAPI entrypoint for the Club Commerce WhatsApp Agent.

W2 keeps WhatsApp mocked. Real Meta/Twilio adapters can call the same agent
service once provider credentials are configured in W3/W4.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import PlainTextResponse

from .api_auth import agent_api_key_valid
from .anthropic_client import AnthropicClient
from .brain import ClaudeSalesBrain
from .config import load_settings
from .crm_client import CRMClient, CRMClientError
from .memory import ConversationMemory
from .providers import build_provider
from .providers.base import WhatsAppProviderError
from .security import mask_phone
from .tools import CRMSalesTools
from .webhook_handler import WebhookHTTPError, process_webhook_body


logger = logging.getLogger("club_commerce.whatsapp_agent")

settings = load_settings()
crm_client = CRMClient(settings.crm_api_url, settings.crm_api_key)
sales_tools = CRMSalesTools(crm_client)
memory = ConversationMemory(settings.memory_path)
anthropic_client = AnthropicClient(settings.anthropic_api_key, settings.anthropic_model)
seller_brain = ClaudeSalesBrain(sales_tools, memory, anthropic_client, settings.ai_qualification_min_score)
whatsapp_provider = build_provider(settings)
START_TIME = time.time()

app = FastAPI(title="Club Commerce WhatsApp Sales Agent", version="0.4.0")


def runtime_commit() -> str:
    for key in ("RENDER_GIT_COMMIT", "RAILWAY_GIT_COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA", "GIT_COMMIT"):
        value = os.getenv(key, "").strip()
        if value:
            return value[:12]
    return "local"


class SimulateMessage(BaseModel):
    phone: str = Field(..., min_length=5)
    message: str = Field(..., min_length=1)
    name: str | None = None
    email: str | None = None


class SendMessagePayload(BaseModel):
    phone: str = Field(..., min_length=5)
    message: str = Field(..., min_length=1, max_length=1500)
    leadId: str | None = None


class SendTemplatePayload(BaseModel):
    phone: str = Field(..., min_length=5)
    templateName: str = Field(..., min_length=1, max_length=120)
    languageCode: str = Field(default="en_US", min_length=2, max_length=20)
    components: list[dict[str, Any]] = Field(default_factory=list)


def require_agent_api_key(api_key: str | None) -> None:
    if not agent_api_key_valid(api_key, settings.agent_api_key):
        raise HTTPException(status_code=401, detail="Invalid agent API key")


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "club-commerce-whatsapp-agent",
        "health": "/health",
    }


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
        "qualificationMinScore": settings.ai_qualification_min_score,
        "qualificationLanguage": settings.ai_qualification_language,
    }


@app.get("/debug/config")
def debug_config() -> dict[str, Any]:
    """Non-secret runtime config for production dry runs."""
    return {
        "ok": True,
        "provider": settings.whatsapp_provider,
        "crmConfigured": settings.crm_ready,
        "claudeConfigured": anthropic_client.ready,
        "metaConfigured": bool(
            settings.meta_access_token
            and settings.meta_phone_number_id
            and settings.meta_verify_token
            and settings.meta_app_secret
        ),
        "graphVersion": settings.meta_graph_version,
        "qualificationMinScore": settings.ai_qualification_min_score,
        "qualificationLanguage": settings.ai_qualification_language,
    }


@app.get("/debug/status")
def debug_status() -> dict[str, Any]:
    """Non-secret operational status for production checks."""
    return {
        "ok": True,
        "provider": settings.whatsapp_provider,
        "crmConfigured": settings.crm_ready,
        "claudeConfigured": anthropic_client.ready,
        "metaConfigured": bool(
            settings.meta_access_token
            and settings.meta_phone_number_id
            and settings.meta_verify_token
            and settings.meta_app_secret
        ),
        "memoryPath": settings.memory_path,
        "qualificationMinScore": settings.ai_qualification_min_score,
        "qualificationLanguage": settings.ai_qualification_language,
        "uptime": round(time.time() - START_TIME, 2),
        "version": app.version,
        "commit": runtime_commit(),
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


@app.post("/api/send-message")
def send_message(payload: SendMessagePayload, x_agent_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_agent_api_key(x_agent_api_key)
    if settings.whatsapp_provider != "meta" or getattr(whatsapp_provider, "name", "") != "meta":
        raise HTTPException(status_code=409, detail="WhatsApp real send requires WHATSAPP_PROVIDER=meta")

    logger.info(
        "POST /api/send-message provider=%s phone=%s lead=%s",
        getattr(whatsapp_provider, "name", "unknown"),
        mask_phone(payload.phone),
        payload.leadId or "",
    )
    try:
        result = whatsapp_provider.send_message(payload.phone, payload.message.strip())
    except WhatsAppProviderError as exc:
        logger.warning("Manual WhatsApp send failed phone=%s error=%s", mask_phone(payload.phone), type(exc).__name__)
        raise HTTPException(status_code=502, detail="WhatsApp provider send failed") from exc

    response = result.get("response") if isinstance(result, dict) else {}
    messages = response.get("messages") if isinstance(response, dict) else []
    provider_message_id = ""
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        provider_message_id = str(messages[0].get("id") or "")
    return {"ok": True, "providerMessageId": provider_message_id}


@app.post("/api/send-template")
def send_template(payload: SendTemplatePayload, x_agent_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_agent_api_key(x_agent_api_key)
    if settings.whatsapp_provider != "meta" or getattr(whatsapp_provider, "name", "") != "meta":
        raise HTTPException(status_code=409, detail="WhatsApp template send requires WHATSAPP_PROVIDER=meta")

    logger.info(
        "POST /api/send-template provider=%s phone=%s template=%s",
        getattr(whatsapp_provider, "name", "unknown"),
        mask_phone(payload.phone),
        payload.templateName,
    )
    try:
        result = whatsapp_provider.send_template(
            payload.phone,
            payload.templateName.strip(),
            payload.languageCode.strip() or "en_US",
            payload.components,
        )
    except WhatsAppProviderError as exc:
        logger.warning(
            "WhatsApp template send failed phone=%s template=%s error=%s",
            mask_phone(payload.phone),
            payload.templateName,
            type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="WhatsApp provider template send failed") from exc

    response = result.get("response") if isinstance(result, dict) else {}
    messages = response.get("messages") if isinstance(response, dict) else []
    provider_message_id = ""
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        provider_message_id = str(messages[0].get("id") or "")
    return {"ok": True, "providerMessageId": provider_message_id}


@app.get("/webhook")
def verify_webhook(request: Request) -> PlainTextResponse:
    challenge = whatsapp_provider.verify_webhook(request)
    if not challenge:
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    return PlainTextResponse(challenge)


@app.post("/webhook")
async def receive_webhook(request: Request) -> dict[str, Any]:
    try:
        return await process_webhook_body(
            await request.body(),
            request.headers.get("X-Hub-Signature-256"),
            current_settings=settings,
            provider=whatsapp_provider,
            brain=seller_brain,
        )
    except WebhookHTTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("POST /webhook unhandled failure error=%s", type(exc).__name__)
        return {"ok": True, "accepted": False, "error": "unhandled_webhook_error"}
