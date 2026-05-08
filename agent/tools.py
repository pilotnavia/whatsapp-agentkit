"""Agent tools backed by the Club Commerce CRM Bridge."""

from __future__ import annotations

import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol


logger = logging.getLogger("club_commerce.whatsapp_agent")


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


def mask_phone(value: str | None) -> str:
    normalized = normalize_phone(value)
    if len(normalized) <= 4:
        return "***"
    return f"***{normalized[-4:]}"


def utc_in(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _clean_label_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:500]


def _add_answer(answers: list[dict[str, str]], label: str, value: str, key: str) -> None:
    clean = _clean_label_value(value)
    if not clean:
        return
    item = {"label": label, "value": clean, "key": key}
    if item not in answers:
        answers.append(item)


def _match_budget(text: str) -> str:
    patterns = (
        r"(?:presupuesto|budget|tengo|invertir|inversion|inversi[oó]n)\D{0,25}(\$?\s?\d[\d,.]{1,10})",
        r"(\$?\s?\d[\d,.]{2,10})\s?(?:usd|dolares|d[oó]lares|para invertir|de presupuesto)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return _clean_label_value(match.group(1))
    return ""


def ecommerce_context_from_message(message: str, intent: str | None = None) -> dict[str, Any]:
    text = message.casefold()
    answers: list[dict[str, str]] = []
    topics: list[str] = []
    summary_bits: list[str] = []

    topic_rules = (
        ("Ecommerce general", "ecommerce_general", ("ecommerce", "e-commerce", "vender online", "negocio online")),
        ("Shopify", "shopify", ("shopify", "tienda", "checkout", "pagina", "página")),
        ("Meta Ads", "meta_ads", ("meta ads", "facebook ads", "anuncios", "ads", "pixel", "campaña", "campana")),
        ("Dropshipping", "dropshipping", ("dropshipping", "drop shipping")),
        ("Importacion desde China", "china_import", ("china", "alibaba", "aliexpress", "importar", "proveedor", "proveedores", "muestras", "moq")),
        ("Producto ganador", "product_validation", ("producto ganador", "validar producto", "producto", "nicho", "margen")),
        ("Marca", "brand", ("marca", "branding", "brand")),
        ("Embudo", "funnels", ("embudo", "funnel", "landing", "conversion", "conversión")),
        ("Contenido organico", "organic_content", ("organico", "orgánico", "tiktok", "reels", "contenido")),
    )
    for label, key, keywords in topic_rules:
        if any(word in text for word in keywords):
            topics.append(key)
            _add_answer(answers, "Interes principal", label, f"interest_{key}")

    if any(word in text for word in ("desde cero", "empezando", "principiante", "no se", "no sé", "nuevo")):
        _add_answer(answers, "Nivel ecommerce", "Empezando desde cero", "ecommerce_level")
        summary_bits.append("Lead empezando desde cero")
    elif any(word in text for word in ("ya vendo", "vendo online", "tengo ventas", "facturo", "escala", "escalar")):
        _add_answer(answers, "Nivel ecommerce", "Ya vende online", "ecommerce_level")
        summary_bits.append("Lead ya vende online")

    if any(word in text for word in ("no tengo tienda", "sin tienda", "no he creado tienda")):
        _add_answer(answers, "Tienda", "No tiene tienda", "store_status")
    elif any(word in text for word in ("tengo tienda", "ya tengo tienda", "mi tienda")):
        _add_answer(answers, "Tienda", "Tiene tienda", "store_status")

    if any(word in text for word in ("perdi dinero", "perdí dinero", "perdi plata", "perdí plata", "ads no funcionaron")):
        _add_answer(answers, "Meta Ads", "Ya probo anuncios y perdio dinero", "ads_status")
        _add_answer(answers, "Objecion principal", "Perdio dinero en ads", "main_objection")
        summary_bits.append("Objecion: perdio dinero en ads")
    elif any(word in text for word in ("ya corro ads", "corro anuncios", "hago anuncios", "tengo campañas", "tengo campanas")):
        _add_answer(answers, "Meta Ads", "Ya corre anuncios", "ads_status")
    elif any(word in text for word in ("nunca he corrido ads", "no corro ads", "no he hecho anuncios")):
        _add_answer(answers, "Meta Ads", "No ha corrido anuncios", "ads_status")

    if any(word in text for word in ("no tengo producto", "sin producto", "no se que vender", "no sé qué vender")):
        _add_answer(answers, "Producto", "No tiene producto definido", "product_status")
        _add_answer(answers, "Objecion principal", "No tiene producto", "main_objection")

    budget = _match_budget(message)
    if budget:
        _add_answer(answers, "Presupuesto aproximado", budget, "budget")
        summary_bits.append(f"Presupuesto aproximado: {budget}")

    if intent:
        _add_answer(answers, "Intencion detectada", intent, "agent_detected_intent")

    if "price_objection" == intent or any(word in text for word in ("caro", "muy caro", "no tengo dinero")):
        _add_answer(answers, "Objecion principal", "Precio/presupuesto", "main_objection")
    if "time_objection" == intent or any(word in text for word in ("no tengo tiempo", "ocupado", "tiempo")):
        _add_answer(answers, "Objecion principal", "Tiempo", "main_objection")
    if "ready_for_handoff" == intent:
        _add_answer(answers, "Urgencia", "Intencion fuerte de compra o llamada", "urgency")

    recommended = ""
    if any(topic in topics for topic in ("china_import",)) or any(word in text for word in ("avanzado", "escala", "escalar", "soporte avanzado")):
        recommended = "100X Elite"
    elif any(word in text for word in ("acompañamiento", "acompanamiento", "mentor", "perdi dinero", "ads")):
        recommended = "100X Pro"
    elif topics or budget or any(word in text for word in ("desde cero", "empezando", "no tengo producto", "shopify")):
        recommended = "100X Academy"
    if any(word in text for word in ("mensual", "cuotas", "pago mensual", "facilidad de pago")):
        _add_answer(answers, "Facilidad de pago", "Pregunto por pago mensual/cuotas", "payment_preference")
    if recommended:
        _add_answer(answers, "Producto recomendado", recommended, "recommended_product")
        summary_bits.append(f"Recomendado: {recommended}")

    if not summary_bits and topics:
        summary_bits.append("Lead pregunta por " + ", ".join(topics[:3]).replace("_", " "))
    summary = " | ".join(summary_bits)
    return {"answers": answers, "summary": summary, "topics": topics, "recommendedProduct": recommended}


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
        sales_context = ecommerce_context_from_message(message, intent)
        intake_answer = {
            "label": "Mensaje WhatsApp",
            "value": message,
            "key": "whatsapp_message",
        }
        answers = [intake_answer, *sales_context["answers"]]
        summary = sales_context["summary"] or f"WhatsApp: {message}".strip()[:1000]
        payload = {
            "phone": clean_phone,
            "email": email,
            "name": name,
            "source": "WhatsApp",
            "campaign": "WhatsApp AI Agent",
            "stage": stage,
            "notes": f"WhatsApp AI: {message}".strip(),
            "intake": {
                "summary": summary[:1000],
                "answers": answers,
                "sourcePayload": {
                    "platform": "whatsapp",
                    "phone": clean_phone,
                    "topics": sales_context["topics"],
                    "recommendedProduct": sales_context["recommendedProduct"],
                },
            },
            "meta": {
                "intent": intent,
                "lastInboundMessage": message,
                "whatsappPhone": clean_phone,
                "channel": "whatsapp",
            },
        }
        try:
            response = self.crm.upsert_lead(payload)
        except Exception as exc:
            logger.warning("CRM upsert failed phone=%s error=%s", mask_phone(clean_phone), type(exc).__name__)
            raise
        logger.info("CRM upsert success phone=%s ok=%s", mask_phone(clean_phone), bool(response.get("ok", True)))
        return response

    def create_followup(
        self,
        lead_id: str,
        note: str,
        minutes_from_now: int = 1440,
        followup_type: str = "whatsapp",
    ) -> dict[str, Any]:
        try:
            response = self.crm.create_followup(
                lead_id=lead_id,
                scheduled_at=utc_in(minutes_from_now),
                note=note,
                followup_type=followup_type,
                status="pending",
            )
        except Exception as exc:
            logger.warning("CRM follow-up failed lead=%s error=%s", lead_id, type(exc).__name__)
            raise
        logger.info("CRM follow-up success lead=%s ok=%s", lead_id, bool(response.get("ok", True)))
        return response

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
        handoff_trigger: str = "",
        handoff_summary: str = "",
        recommended_next_step: str = "",
        confidence: str = "medium",
    ) -> dict[str, Any]:
        clean_phone = normalize_phone(phone)
        try:
            response = self.crm.request_human_handoff(
                lead_id=lead_id,
                phone=clean_phone,
                email=email,
                reason=reason,
                note=note,
                handoff_trigger=handoff_trigger,
                handoff_summary=handoff_summary,
                recommended_next_step=recommended_next_step,
                confidence=confidence,
            )
        except Exception as exc:
            logger.warning("CRM handoff failed lead=%s phone=%s error=%s", lead_id, mask_phone(clean_phone), type(exc).__name__)
            raise
        logger.info("CRM handoff success lead=%s phone=%s ok=%s", lead_id, mask_phone(clean_phone), bool(response.get("ok", True)))
        return response

    def get_products(self) -> list[dict[str, Any]]:
        response = self.crm.get_products()
        products = response.get("products", response if isinstance(response, list) else [])
        return products if isinstance(products, list) else []
