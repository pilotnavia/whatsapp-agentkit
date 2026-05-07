"""Provider-neutral webhook handling that does not depend on FastAPI."""

from __future__ import annotations

import json
import logging
from typing import Any

from .security import mask_phone, verify_meta_signature


logger = logging.getLogger("club_commerce.whatsapp_agent")


class WebhookHTTPError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    fields: list[str] = []
    entries = payload.get("entry") if isinstance(payload, dict) else None
    if isinstance(entries, list):
        for entry in entries:
            changes = entry.get("changes") if isinstance(entry, dict) else None
            if isinstance(changes, list):
                for change in changes:
                    if isinstance(change, dict) and change.get("field"):
                        fields.append(str(change.get("field")))
    return {
        "object": payload.get("object"),
        "fields": fields,
        "hasEntry": isinstance(entries, list) and bool(entries),
    }


def has_meta_messages(payload: dict[str, Any]) -> bool:
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return False
    for entry in entries:
        changes = entry.get("changes") if isinstance(entry, dict) else None
        if not isinstance(changes, list):
            continue
        for change in changes:
            value = change.get("value") if isinstance(change, dict) else None
            messages = value.get("messages") if isinstance(value, dict) else None
            if isinstance(messages, list) and messages:
                return True
    return False


def whatsapp_mode_from_lead(lead: dict[str, Any] | None) -> str:
    if not isinstance(lead, dict):
        return "bot"
    whatsapp = lead.get("whatsapp")
    if not isinstance(whatsapp, dict):
        meta = lead.get("meta")
        whatsapp = meta.get("whatsapp") if isinstance(meta, dict) else {}
    mode = str((whatsapp or {}).get("mode") or "bot").strip().lower()
    return mode if mode in {"bot", "human", "handoff"} else "bot"


def should_pause_for_human_takeover(brain: Any, inbound: Any) -> dict[str, Any]:
    tools = getattr(brain, "tools", None)
    if not tools or not hasattr(tools, "lookup_lead"):
        return {"pause": False}
    lookup = tools.lookup_lead(phone=getattr(inbound, "phone", None), email=getattr(inbound, "email", None))
    lead = lookup.get("lead") if isinstance(lookup, dict) else None
    mode = whatsapp_mode_from_lead(lead)
    if mode not in {"human", "handoff"}:
        return {"pause": False, "mode": mode, "lead": lead}

    lead_id = lead.get("id") if isinstance(lead, dict) else None
    try:
        if hasattr(tools, "log_activity"):
            tools.log_activity(
                "WhatsApp inbound recibido sin respuesta automatica por takeover humano",
                lead_id=lead_id,
                activity_type="whatsapp_inbound_paused",
                meta={
                    "mode": mode,
                    "channel": "whatsapp",
                    "messagePreview": str(getattr(inbound, "text", "") or "")[:180],
                },
            )
    except Exception as exc:
        logger.warning(
            "POST /webhook pause activity failed phone=%s error=%s",
            mask_phone(getattr(inbound, "phone", None)),
            type(exc).__name__,
        )
    return {"pause": True, "mode": mode, "lead": lead}


async def process_webhook_body(
    body: bytes,
    signature_header: str | None,
    *,
    current_settings: Any,
    provider: Any,
    brain: Any,
) -> dict[str, Any]:
    logger.info(
        "POST /webhook received provider=%s signature_present=%s",
        getattr(current_settings, "whatsapp_provider", "unknown"),
        bool(signature_header),
    )

    if getattr(current_settings, "whatsapp_provider", "") == "meta":
        if not signature_header:
            logger.warning("missing meta signature")
            raise WebhookHTTPError(401, "Missing webhook signature")
        if not verify_meta_signature(body, signature_header, getattr(current_settings, "meta_app_secret", "")):
            logger.warning("invalid meta signature")
            raise WebhookHTTPError(401, "Invalid webhook signature")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        logger.warning("POST /webhook invalid JSON")
        raise WebhookHTTPError(400, "Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        logger.warning("POST /webhook invalid payload type")
        raise WebhookHTTPError(400, "Invalid webhook payload")

    summary = payload_summary(payload)
    logger.info(
        "POST /webhook payload summary provider=%s object=%s fields=%s",
        getattr(provider, "name", "unknown"),
        summary["object"],
        ",".join(summary["fields"]) if summary["fields"] else "none",
    )

    if getattr(provider, "name", "") == "meta" and not has_meta_messages(payload):
        logger.info("POST /webhook ignored: no messages")
        return {"ok": True, "ignored": True}

    try:
        inbound = provider.parse_webhook(payload)
    except Exception as exc:
        logger.exception(
            "POST /webhook provider parse failed provider=%s error=%s",
            getattr(provider, "name", "unknown"),
            type(exc).__name__,
        )
        return {
            "ok": True,
            "accepted": False,
            "error": "parse_failed",
            "provider": getattr(provider, "name", "unknown"),
        }

    if not inbound:
        logger.info("POST /webhook ignored: provider returned no inbound message")
        return {"ok": True, "ignored": True}

    try:
        pause = should_pause_for_human_takeover(brain, inbound)
        if pause.get("pause"):
            logger.info(
                "POST /webhook auto reply paused mode=%s phone=%s",
                pause.get("mode"),
                mask_phone(getattr(inbound, "phone", None)),
            )
            return {
                "ok": True,
                "ignored": True,
                "paused": True,
                "mode": pause.get("mode"),
                "leadId": ((pause.get("lead") or {}) if isinstance(pause.get("lead"), dict) else {}).get("id"),
            }
        reply = brain.handle_message(
            phone=inbound.phone,
            message=inbound.text,
            name=inbound.name,
            email=inbound.email,
        )
        send_result = provider.send_message(inbound.phone, reply.message)
    except Exception as exc:
        logger.exception(
            "POST /webhook processing failed provider=%s phone=%s error=%s",
            getattr(provider, "name", "unknown"),
            mask_phone(getattr(inbound, "phone", None)),
            type(exc).__name__,
        )
        return {
            "ok": True,
            "accepted": False,
            "error": "processing_failed",
            "provider": getattr(provider, "name", "unknown"),
        }

    return {
        "ok": True,
        "provider": provider.name,
        "phone": mask_phone(inbound.phone),
        "intent": reply.intent,
        "handoff": reply.handoff,
        "leadId": (reply.lead or {}).get("id"),
        "sent": send_result.get("ok", False),
    }
