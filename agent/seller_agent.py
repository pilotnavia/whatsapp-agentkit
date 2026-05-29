"""Practical WhatsApp seller agent for local W2 testing.

This version is intentionally deterministic. It exercises the CRM Bridge tools
without calling a model provider yet, so W2 can be validated without WhatsApp or
Claude credentials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .sales_prompt import ECOMMERCE_PLAYBOOK, OBJECTION_GUIDE, SYSTEM_PROMPT
from .tools import CRMSalesTools, ai_qualification_from_message


STRONG_INTENT = (
    "comprar",
    "buy",
    "pagar",
    "pay",
    "payment",
    "inscribir",
    "inscribirme",
    "sign up",
    "enroll",
    "quiero entrar",
    "i want to join",
    "i want in",
    "link",
    "checkout",
    "tarjeta",
    "zelle",
    "paypal",
    "llamada",
    "call",
    "call me",
    "asesor",
    "advisor",
    "humano",
    "human",
    "persona",
    "person",
    "talk to someone",
)

PRICE_INTENT = ("precio", "cuanto", "cuánto", "cost", "price", "pricing", "how much", "vale", "plan", "planes")
ANGER_INTENT = ("molesto", "estafa", "enojo", "enojado", "reclamo", "queja", "angry", "scam", "complaint")
HOT_STAGE_WORDS = ("interesa", "interesado", "me sirve", "quiero", "listo", "ready", "interested", "i want")
ECOMMERCE_GENERAL_INTENT = (
    "ecommerce",
    "e-commerce",
    "vender online",
    "negocio online",
    "ventas online",
    "sell online",
    "online store",
    "online business",
)
SHOPIFY_INTENT = ("shopify", "tienda", "store", "checkout", "pagina", "página", "sales")
META_ADS_INTENT = ("meta ads", "facebook ads", "anuncios", "ads", "pixel", "campaña", "campana")
DROPSHIPPING_INTENT = ("dropshipping", "drop shipping")
CHINA_IMPORT_INTENT = ("china", "alibaba", "importar", "proveedor", "proveedores", "muestras", "moq")
PRODUCT_INTENT = (
    "producto ganador",
    "validar producto",
    "no tengo producto",
    "que vender",
    "qué vender",
    "nicho",
    "winning product",
    "what to sell",
    "niche",
)
BRAND_INTENT = ("marca", "branding", "brand")
FUNNEL_INTENT = ("embudo", "funnel", "landing", "conversion", "conversión")
INFO_INTENT = ("mandame info", "mándame info", "informacion", "información", "info", "send me info", "information")
EXPERIENCE_INTENT = (
    "nuevo",
    "empezando",
    "experiencia",
    "starting",
    "beginner",
    "from scratch",
    "start from zero",
    "desde cero",
)


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


def _training_context(tools: CRMSalesTools) -> dict[str, Any]:
    if hasattr(tools, "get_training_context"):
        context = tools.get_training_context()
        return context if isinstance(context, dict) else {}
    return {}


def _active_training_products(context: dict[str, Any]) -> list[dict[str, Any]]:
    products = context.get("activeProducts") if isinstance(context, dict) else []
    return products if isinstance(products, list) else []


def _matches_opt_out(message: str, context: dict[str, Any]) -> bool:
    rules = context.get("aiRules") if isinstance(context, dict) else {}
    keywords = rules.get("optOutKeywords") if isinstance(rules, dict) and isinstance(rules.get("optOutKeywords"), list) else []
    if not keywords:
        keywords = ["stop", "cancelar", "no me escribas", "salir", "unsubscribe"]
    text = message.casefold()
    return any(str(keyword or "").strip().casefold() in text for keyword in keywords if str(keyword or "").strip())


def _matching_faq_answer(message: str, context: dict[str, Any]) -> str:
    faqs = context.get("activeFaqs") if isinstance(context, dict) else []
    if not isinstance(faqs, list):
        return ""
    text = message.casefold()
    for faq in faqs[:12]:
      if not isinstance(faq, dict):
          continue
      question = str(faq.get("question") or "")
      answer = str(faq.get("answer") or "")
      tokens = [token for token in re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]{4,}", question.casefold()) if token not in {"como", "para", "porque", "cuando"}]
      if answer and tokens and sum(1 for token in tokens if token in text) >= 1:
          return answer[:900]
    return ""


def _detect_intent(message: str) -> str:
    text = _lower(message)
    if any(word in text for word in ANGER_INTENT):
        return "needs_human"
    if any(word in text for word in STRONG_INTENT):
        return "ready_for_handoff"
    if any(word in text for word in PRICE_INTENT):
        return "pricing"
    if any(word in text for word in META_ADS_INTENT) and any(word in text for word in ("perdi", "perdí", "perder", "queme", "quemé")):
        return "meta_ads_lost_money"
    if re.search(r"(presupuesto|budget).{0,30}(\$?\s?\d[\d,.]{1,10})", text):
        return "budget_capture"
    if "caro" in text or "dinero" in text or "presupuesto" in text:
        return "price_objection"
    if "tiempo" in text or "ocupado" in text:
        return "time_objection"
    if "confio" in text or "confío" in text or "seguro" in text:
        return "trust_objection"
    if any(word in text for word in SHOPIFY_INTENT):
        return "shopify_question"
    if any(word in text for word in META_ADS_INTENT):
        return "meta_ads_question"
    if any(word in text for word in DROPSHIPPING_INTENT):
        return "dropshipping_question"
    if any(word in text for word in CHINA_IMPORT_INTENT):
        return "china_import_question"
    if any(word in text for word in PRODUCT_INTENT):
        return "product_validation"
    if any(word in text for word in BRAND_INTENT):
        return "brand_question"
    if any(word in text for word in FUNNEL_INTENT):
        return "funnels_question"
    if any(word in text for word in INFO_INTENT):
        return "info_request"
    if any(word in text for word in ECOMMERCE_GENERAL_INTENT):
        return "ecommerce_general"
    if any(word in text for word in EXPERIENCE_INTENT):
        return "experience_question"
    if any(word in text for word in HOT_STAGE_WORDS):
        return "interested"
    return "discovery"


class ClubCommerceSellerAgent:
    def __init__(self, tools: CRMSalesTools, qualification_min_score: int = 70):
        self.tools = tools
        self.qualification_min_score = qualification_min_score
        self.system_prompt = SYSTEM_PROMPT

    def handle_message(
        self,
        phone: str,
        message: str,
        name: str | None = None,
        email: str | None = None,
    ) -> AgentReply:
        intent = _detect_intent(message)
        stage = "interesado" if intent in {"pricing", "interested", "ready_for_handoff", "budget_capture"} else "conversacion"
        training_context = _training_context(self.tools)

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

        if _matches_opt_out(message, training_context):
            self.tools.log_activity(
                "Lead solicito opt-out por WhatsApp",
                lead_id=lead_id,
                activity_type="whatsapp_opt_out",
                meta={"channel": "whatsapp", "sender": "system", "messagePreview": message[:180]},
            )
            return AgentReply(
                "Listo, no te enviaremos mas mensajes automaticos. Si necesitas ayuda luego, puedes escribirnos por aqui.",
                lead,
                "opt_out",
                tool_results=tool_results,
            )

        rules = training_context.get("aiRules") if isinstance(training_context.get("aiRules"), dict) else {}
        if rules.get("autoReplyEnabled") is False:
            handoff = self.tools.request_human_handoff(
                lead_id=lead_id,
                phone=phone,
                email=email,
                reason="Auto reply pausado por reglas AI del CRM",
                note=message,
                handoff_trigger="auto_reply_disabled",
                handoff_summary="El CRM tiene autoReplyEnabled=false.",
                recommended_next_step="Responder manualmente desde WhatsApp Inbox.",
                confidence="medium",
            )
            tool_results["handoff"] = handoff
            return AgentReply(
                "Gracias por escribirnos. Un asesor del equipo te respondera personalmente por aqui.",
                lead,
                "auto_reply_disabled",
                handoff=True,
                tool_results=tool_results,
            )

        if intent in {"ready_for_handoff", "needs_human"}:
            reason = "Lead listo para humano" if intent == "ready_for_handoff" else "Lead requiere atencion humana"
            trigger = "human_request" if intent == "needs_human" else "high_intent"
            summary = (
                "El lead pidio atencion humana."
                if intent == "needs_human"
                else "El lead mostro intencion fuerte de compra o avanzar al pago."
            )
            handoff = self.tools.request_human_handoff(
                lead_id=lead_id,
                phone=phone,
                email=email,
                reason=reason,
                note=message,
                handoff_trigger=trigger,
                handoff_summary=summary,
                recommended_next_step="Tomar la conversacion, confirmar necesidad y guiar al siguiente paso.",
                confidence="high" if intent == "ready_for_handoff" else "medium",
            )
            tool_results["handoff"] = handoff
            self._maybe_submit_qualification(lead_id, message, intent, tool_results)
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
            products = _active_training_products(training_context) or self.tools.get_products()
            tool_results["products"] = products
            self._safe_followup(lead_id, "Enviar seguimiento de precios por WhatsApp", 180)
            self._maybe_submit_qualification(lead_id, message, intent, tool_results)
            return AgentReply(
                message=(
                    "Claro. Estas son las ofertas que tengo disponibles:\n"
                    f"{_format_products(products)}\n"
                    "Cual te interesa revisar primero?"
                ),
                lead=lead,
                intent=intent,
                tool_results=tool_results,
            )

        if intent == "price_objection":
            self._safe_followup(lead_id, "Seguimiento por objecion de precio", 1440)
            self._maybe_submit_qualification(lead_id, message, intent, tool_results)
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

        if intent == "budget_capture":
            self._safe_followup(lead_id, "Revisar presupuesto declarado por WhatsApp", 720)
            self._maybe_submit_qualification(lead_id, message, intent, tool_results)
            return AgentReply(
                "Perfecto, con ese presupuesto conviene priorizar producto, tienda y validacion antes de escalar ads. "
                "Ya tienes producto definido o necesitas ayuda encontrando uno?",
                lead,
                intent,
                tool_results=tool_results,
            )

        faq_answer = _matching_faq_answer(message, training_context)
        if faq_answer:
            self._safe_followup(lead_id, "Seguimiento por FAQ respondida por WhatsApp AI", 1440)
            return AgentReply(
                f"{faq_answer}\n\nPara guiarte mejor: ya vendes online o estas empezando desde cero?",
                lead,
                "faq_answer",
                tool_results=tool_results,
            )

        ecommerce_reply = self._ecommerce_reply(intent)
        if ecommerce_reply:
            self.tools.log_activity(
                f"Insight WhatsApp AI: {intent}",
                lead_id=lead_id,
                activity_type="agent_insight",
                meta={"intent": intent, "channel": "whatsapp", "messagePreview": message[:180]},
            )
            self._safe_followup(lead_id, f"Dar seguimiento a consulta {intent}", 1440)
            self._maybe_submit_qualification(lead_id, message, intent, tool_results)
            return AgentReply(ecommerce_reply, lead, intent, tool_results=tool_results)

        if not name and not self._lead_has_name(lead):
            self._safe_followup(lead_id, "Pedir nombre y contexto del prospecto", 1440)
            return AgentReply(
                "Claro, te ayudo. Primero dime tu nombre y si ya vendes online o estas empezando desde cero.",
                lead,
                intent,
                tool_results=tool_results,
            )

        self._safe_followup(lead_id, "Dar seguimiento inicial de WhatsApp AI", 1440)
        self._maybe_submit_qualification(lead_id, message, intent, tool_results)
        return AgentReply(
            "Buenisimo. Para recomendarte bien: ya tienes tienda online o estas empezando desde cero?",
            lead,
            intent,
            tool_results=tool_results,
        )

    def _maybe_submit_qualification(
        self,
        lead_id: str | None,
        message: str,
        intent: str,
        tool_results: dict[str, Any],
    ) -> dict[str, Any]:
        qualification = ai_qualification_from_message(message, intent, self.qualification_min_score)
        result = self.tools.submit_ai_qualification(lead_id, qualification)
        if not result.get("skipped"):
            tool_results["qualification"] = result
        if lead_id and hasattr(self.tools, "propose_sales_action"):
            if intent in {"ready_for_handoff", "needs_human"}:
                action = self.tools.propose_sales_action(
                    lead_id=lead_id,
                    phone=None,
                    action_type="request_handoff",
                    priority="high",
                    title="Lead listo para humano",
                    reasoning="El fallback detecto intencion fuerte o peticion humana.",
                    recommended_message=message[:500],
                    metadata={"intent": intent, "score": qualification.get("score"), "nextBestAction": "Tomar la conversacion"},
                )
            elif intent in {"pricing", "price_objection", "interested", "budget_capture"}:
                action = self.tools.propose_sales_action(
                    lead_id=lead_id,
                    phone=None,
                    action_type="create_followup",
                    priority="medium",
                    title="Seguimiento comercial recomendado",
                    reasoning="El fallback detecto interes comercial y recomienda seguimiento.",
                    recommended_message=message[:500],
                    metadata={"intent": intent, "score": qualification.get("score")},
                )
            else:
                action = None
            if action and not action.get("skipped"):
                tool_results["salesAction"] = action
        return result

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

    @staticmethod
    def _ecommerce_reply(intent: str) -> str:
        mapping = {
            "shopify_question": ECOMMERCE_PLAYBOOK["shopify"],
            "meta_ads_question": ECOMMERCE_PLAYBOOK["meta_ads"],
            "meta_ads_lost_money": OBJECTION_GUIDE["ads"],
            "dropshipping_question": ECOMMERCE_PLAYBOOK["dropshipping"],
            "china_import_question": ECOMMERCE_PLAYBOOK["china_import"],
            "product_validation": ECOMMERCE_PLAYBOOK["product_validation"],
            "brand_question": ECOMMERCE_PLAYBOOK["brand"],
            "funnels_question": ECOMMERCE_PLAYBOOK["funnels"],
            "info_request": OBJECTION_GUIDE["info"],
            "ecommerce_general": ECOMMERCE_PLAYBOOK["ecommerce_general"],
        }
        return mapping.get(intent, "")
