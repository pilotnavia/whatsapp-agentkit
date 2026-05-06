"""Practical WhatsApp seller agent for local W2 testing.

This version is intentionally deterministic. It exercises the CRM Bridge tools
without calling a model provider yet, so W2 can be validated without WhatsApp or
Claude credentials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .sales_prompt import OBJECTION_GUIDE, SYSTEM_PROMPT
from .tools import CRMSalesTools


STRONG_INTENT = (
    "comprar",
    "pagar",
    "inscribir",
    "inscribirme",
    "quiero entrar",
    "link",
    "checkout",
    "tarjeta",
    "zelle",
    "paypal",
    "llamada",
    "asesor",
    "humano",
    "persona",
)

PRICE_INTENT = ("precio", "cuanto", "cuánto", "cost", "vale", "plan", "planes")
ANGER_INTENT = ("molesto", "estafa", "enojo", "enojado", "reclamo", "queja")
HOT_STAGE_WORDS = ("interesa", "interesado", "me sirve", "quiero", "listo")


@dataclass
class AgentReply:
    message: str
    lead: dict[str, Any] | None
    intent: str
    handoff: bool = False
    tool_results: dict[str, Any] | None = None


def _lower(text: str) -> str:
    return text.casefold().strip()


def _lead_from_response(response: dict[str, Any]) -> dict[str, Any] | None:
    lead = response.get("lead") if isinstance(response, dict) else None
    return lead if isinstance(lead, dict) else None


def _product_price(product: dict[str, Any]) -> str:
    for key in ("price", "amount", "value", "closeValue"):
        value = product.get(key)
        if value not in (None, ""):
            return f"${value}"
    return "precio manual"


def _format_products(products: list[dict[str, Any]]) -> str:
    if not products:
        return "Ahora mismo no tengo precios cargados. Te conecto con el equipo para confirmarlo."
    lines = []
    for product in products[:5]:
        name = product.get("name") or product.get("title") or "Oferta Club Commerce"
        lines.append(f"- {name}: {_product_price(product)}")
    return "\n".join(lines)


def _detect_intent(message: str) -> str:
    text = _lower(message)
    if any(word in text for word in ANGER_INTENT):
        return "needs_human"
    if any(word in text for word in STRONG_INTENT):
        return "ready_for_handoff"
    if any(word in text for word in PRICE_INTENT):
        return "pricing"
    if "caro" in text or "dinero" in text or "presupuesto" in text:
        return "price_objection"
    if "tiempo" in text or "ocupado" in text:
        return "time_objection"
    if "confio" in text or "confío" in text or "seguro" in text:
        return "trust_objection"
    if "nuevo" in text or "empezando" in text or "experiencia" in text:
        return "experience_question"
    if any(word in text for word in HOT_STAGE_WORDS):
        return "interested"
    return "discovery"


class ClubCommerceSellerAgent:
    def __init__(self, tools: CRMSalesTools):
        self.tools = tools
        self.system_prompt = SYSTEM_PROMPT

    def handle_message(
        self,
        phone: str,
        message: str,
        name: str | None = None,
        email: str | None = None,
    ) -> AgentReply:
        intent = _detect_intent(message)
        stage = "interesado" if intent in {"pricing", "interested", "ready_for_handoff"} else "conversacion"

        upsert = self.tools.upsert_lead(
            phone=phone,
            email=email,
            name=name,
            message=message,
            intent=intent,
            stage=stage,
        )
        lead = _lead_from_response(upsert)
        lead_id = lead.get("id") if lead else None

        tool_results: dict[str, Any] = {"upsert": upsert}
        self.tools.log_activity(
            "WhatsApp AI recibio mensaje del lead",
            lead_id=lead_id,
            meta={"intent": intent},
        )

        if intent in {"ready_for_handoff", "needs_human"}:
            reason = "Lead listo para humano" if intent == "ready_for_handoff" else "Lead requiere atencion humana"
            handoff = self.tools.request_human_handoff(
                lead_id=lead_id,
                phone=phone,
                email=email,
                reason=reason,
                note=message,
            )
            tool_results["handoff"] = handoff
            return AgentReply(
                message=(
                    "Perfecto, te conecto con alguien del equipo para ayudarte directo. "
                    "Mientras tanto, dime si prefieres que te escriban por WhatsApp o llamada."
                ),
                lead=lead,
                intent=intent,
                handoff=True,
                tool_results=tool_results,
            )

        if intent == "pricing":
            products = self.tools.get_products()
            tool_results["products"] = products
            self._safe_followup(lead_id, "Enviar seguimiento de precios por WhatsApp", 180)
            return AgentReply(
                message=(
                    "Claro. Estas son las ofertas que tengo disponibles:\n"
                    f"{_format_products(products)}\n\n"
                    "Cual te interesa revisar primero?"
                ),
                lead=lead,
                intent=intent,
                tool_results=tool_results,
            )

        if intent == "price_objection":
            self._safe_followup(lead_id, "Seguimiento por objecion de precio", 1440)
            return AgentReply(OBJECTION_GUIDE["precio"], lead, intent, tool_results=tool_results)

        if intent == "time_objection":
            self._safe_followup(lead_id, "Seguimiento por objecion de tiempo", 1440)
            return AgentReply(OBJECTION_GUIDE["tiempo"], lead, intent, tool_results=tool_results)

        if intent == "trust_objection":
            self._safe_followup(lead_id, "Seguimiento por objecion de confianza", 720)
            return AgentReply(OBJECTION_GUIDE["confianza"], lead, intent, tool_results=tool_results)

        if intent == "experience_question":
            self._safe_followup(lead_id, "Seguimiento de lead nuevo o sin experiencia", 1440)
            return AgentReply(OBJECTION_GUIDE["experiencia"], lead, intent, tool_results=tool_results)

        if not name and not self._lead_has_name(lead):
            self._safe_followup(lead_id, "Pedir nombre y contexto del prospecto", 1440)
            return AgentReply(
                "Claro, te ayudo. Primero dime tu nombre y si ya vendes online o estas empezando desde cero.",
                lead,
                intent,
                tool_results=tool_results,
            )

        self._safe_followup(lead_id, "Dar seguimiento inicial de WhatsApp AI", 1440)
        return AgentReply(
            "Buenisimo. Para recomendarte bien: ya tienes tienda online o estas empezando desde cero?",
            lead,
            intent,
            tool_results=tool_results,
        )

    def _safe_followup(self, lead_id: str | None, note: str, minutes_from_now: int) -> None:
        if not lead_id:
            return
        self.tools.create_followup(lead_id=lead_id, note=note, minutes_from_now=minutes_from_now)

    @staticmethod
    def _lead_has_name(lead: dict[str, Any] | None) -> bool:
        if not lead:
            return False
        name = str(lead.get("name") or "").strip()
        return bool(name and not re.fullmatch(r"lead\s*\d+", name, flags=re.I))

