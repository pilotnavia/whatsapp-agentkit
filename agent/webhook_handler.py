"""Provider-neutral webhook handling that does not depend on FastAPI."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from .security import mask_phone, verify_meta_signature


logger = logging.getLogger("club_commerce.whatsapp_agent")

MAX_INBOUND_MESSAGE_LENGTH = 1500
SEEN_MESSAGE_TTL_SECONDS = 60 * 60 * 24
SEEN_MESSAGE_LIMIT = 5000
_seen_message_ids: dict[str, float] = {}


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
            inbound_text = str(getattr(inbound, "text", "") or "")
            tools.log_activity(
                inbound_text,
                lead_id=lead_id,
                activity_type="whatsapp_inbound",
                meta={
                    "mode": mode,
                    "channel": "whatsapp",
                    "direction": "inbound",
                    "sender": "lead",
                    "body": inbound_text,
                    "text": inbound_text,
                    "messageId": getattr(inbound, "provider_message_id", None),
                    "status": "received",
                },
            )
            tools.log_activity(
                "WhatsApp inbound recibido sin respuesta automatica por takeover humano",
                lead_id=lead_id,
                activity_type="whatsapp_system",
                meta={
                    "mode": mode,
                    "channel": "whatsapp",
                    "sender": "system",
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


def provider_message_id_from_send_result(send_result: dict[str, Any] | None) -> str | None:
    if not isinstance(send_result, dict):
        return None
    for key in ("providerMessageId", "messageId", "id"):
        value = send_result.get(key)
        if value:
            return str(value)
    response = send_result.get("response")
    if isinstance(response, dict):
        messages = response.get("messages")
        if isinstance(messages, list) and messages and isinstance(messages[0], dict):
            value = messages[0].get("id")
            if value:
                return str(value)
    return None


def log_outbound_bot_message(brain: Any, inbound: Any, reply: Any, send_result: dict[str, Any] | None) -> None:
    tools = getattr(brain, "tools", None)
    if not tools or not hasattr(tools, "log_activity"):
        return
    lead = getattr(reply, "lead", None)
    lead_id = lead.get("id") if isinstance(lead, dict) else None
    message = str(getattr(reply, "message", "") or "").strip()
    if not message:
        return
    try:
        tools.log_activity(
            message,
            lead_id=lead_id,
            activity_type="whatsapp_outbound_bot",
            meta={
                "channel": "whatsapp",
                "direction": "outbound",
                "sender": "bot",
                "body": message,
                "text": message,
                "status": "sent" if isinstance(send_result, dict) and send_result.get("ok") else "unknown",
                "messageId": provider_message_id_from_send_result(send_result),
                "intent": getattr(reply, "intent", ""),
                "handoff": bool(getattr(reply, "handoff", False)),
            },
        )
    except Exception as exc:
        logger.warning(
            "POST /webhook outbound transcript log failed phone=%s error=%s",
            mask_phone(getattr(inbound, "phone", None)),
            type(exc).__name__,
        )


def _cleanup_seen_message_ids(now: float) -> None:
    if len(_seen_message_ids) <= SEEN_MESSAGE_LIMIT:
        expired = [key for key, seen_at in _seen_message_ids.items() if now - seen_at > SEEN_MESSAGE_TTL_SECONDS]
    else:
        ordered = sorted(_seen_message_ids.items(), key=lambda item: item[1])
        expired = [key for key, _ in ordered[: max(1, len(ordered) - SEEN_MESSAGE_LIMIT)]]
    for key in expired:
        _seen_message_ids.pop(key, None)


def is_duplicate_message(provider_name: str, provider_message_id: str | None) -> bool:
    message_id = str(provider_message_id or "").strip()
    if not message_id:
        return False
    key = f"{provider_name}:{message_id}"
    now = time.time()
    _cleanup_seen_message_ids(now)
    if key in _seen_message_ids:
        return True
    _seen_message_ids[key] = now
    return False


def reset_seen_messages_for_tests() -> None:
    _seen_message_ids.clear()


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

    provider_name = getattr(provider, "name", "unknown")
    if is_duplicate_message(provider_name, getattr(inbound, "provider_message_id", None)):
        logger.info(
            "POST /webhook ignored duplicate provider=%s messageIdPresent=%s",
            provider_name,
            bool(getattr(inbound, "provider_message_id", None)),
        )
        return {"ok": True, "ignored": True, "duplicate": True}

    inbound_text = str(getattr(inbound, "text", "") or "").strip()
    if not inbound_text:
        logger.info("POST /webhook ignored empty message phone=%s", mask_phone(getattr(inbound, "phone", None)))
        return {"ok": True, "ignored": True, "reason": "empty_message"}
    if len(inbound_text) > MAX_INBOUND_MESSAGE_LENGTH:
        logger.warning(
            "POST /webhook ignored oversized message phone=%s length=%s",
            mask_phone(getattr(inbound, "phone", None)),
            len(inbound_text),
        )
        return {"ok": True, "ignored": True, "reason": "message_too_long"}

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
            message=inbound_text,
            name=inbound.name,
            email=inbound.email,
        )
        logger.info(
            "POST /webhook message processed provider=%s phone=%s intent=%s handoff=%s",
            getattr(provider, "name", "unknown"),
            mask_phone(getattr(inbound, "phone", None)),
            getattr(reply, "intent", ""),
            bool(getattr(reply, "handoff", False)),
        )
        send_result = provider.send_message(inbound.phone, reply.message)
        log_outbound_bot_message(brain, inbound, reply, send_result)
        logger.info(
            "POST /webhook send success provider=%s phone=%s ok=%s",
            getattr(provider, "name", "unknown"),
            mask_phone(getattr(inbound, "phone", None)),
            bool(send_result.get("ok", False)) if isinstance(send_result, dict) else False,
        )
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
