"""Claude-powered sales brain that coordinates CRM tools and memory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from .anthropic_client import AnthropicClientError
from .memory import ConversationMemory
from .sales_prompt import SYSTEM_PROMPT
from .seller_agent import AgentReply, ClubCommerceSellerAgent, _detect_intent
from .tools import CRMSalesTools, ai_qualification_from_message


class ModelClient(Protocol):
    @property
    def ready(self) -> bool: ...
    def complete(self, system: str, messages: list[dict[str, str]], max_tokens: int = 900) -> str: ...


@dataclass
class BrainDecision:
    reply: str
    intent: str
    handoff: bool = False
    needs_followup: bool = True
    followup_note: str = "Seguimiento WhatsApp AI"
    followup_minutes: int = 1440
    stage: str = "conversacion"
    handoff_reason: str = ""
    handoff_trigger: str = ""
    handoff_summary: str = ""
    recommended_next_step: str = ""
    confidence: str = "medium"


class ClaudeSalesBrain:
    def __init__(
        self,
        tools: CRMSalesTools,
        memory: ConversationMemory,
        model: ModelClient | None = None,
        qualification_min_score: int = 70,
    ):
        self.tools = tools
        self.memory = memory
        self.model = model
        self.qualification_min_score = qualification_min_score
        self.fallback_agent = ClubCommerceSellerAgent(tools, qualification_min_score)

    def handle_message(
        self,
        phone: str,
        message: str,
        name: str | None = None,
        email: str | None = None,
    ) -> AgentReply:
        if not self.model or not self.model.ready:
            reply = self.fallback_agent.handle_message(phone, message, name=name, email=email)
            self._remember(phone, message, reply.message, {"intent": reply.intent, "mode": "fallback"})
            return reply

        inferred_intent = _detect_intent(message)
        stage = "interesado" if inferred_intent in {"pricing", "interested", "ready_for_handoff", "budget_capture"} else "conversacion"
        upsert = self.tools.upsert_lead(
            phone=phone,
            email=email,
            name=name,
            message=message,
            intent=inferred_intent,
            stage=stage,
        )
        lead = upsert.get("lead") if isinstance(upsert, dict) else None
        lead_id = lead.get("id") if isinstance(lead, dict) else None

        products = self.tools.get_products() if self._should_load_products(message) else []
        decision = self._decide(phone, message, lead, products, inferred_intent)

        tool_results: dict[str, Any] = {
            "upsert": upsert,
            "products": products,
            "brain": {
                "intent": decision.intent,
                "mode": "claude",
            },
        }

        self.tools.log_activity(
            "Claude WhatsApp AI respondio al lead",
            lead_id=lead_id,
            activity_type="whatsapp_ai_reply",
            meta={"intent": decision.intent, "handoff": decision.handoff},
        )
        if decision.intent in {
            "pricing",
            "interested",
            "price_objection",
            "time_objection",
            "trust_objection",
            "experience_question",
            "ecommerce_general",
            "shopify_question",
            "meta_ads_question",
            "meta_ads_lost_money",
            "dropshipping_question",
            "china_import_question",
            "product_validation",
            "brand_question",
            "funnels_question",
            "budget_capture",
            "info_request",
            "ready_for_handoff",
            "needs_human",
        }:
            self.tools.log_activity(
                f"Insight WhatsApp AI: {decision.intent}",
                lead_id=lead_id,
                activity_type="agent_insight",
                meta={
                    "intent": decision.intent,
                    "channel": "whatsapp",
                    "messagePreview": message[:180],
                },
            )

        if decision.handoff:
            handoff = self.tools.request_human_handoff(
                lead_id=lead_id,
                phone=phone,
                email=email,
                reason=decision.handoff_reason or f"Claude WhatsApp AI: {decision.intent}",
                note=message,
                handoff_trigger=decision.handoff_trigger or decision.intent,
                handoff_summary=decision.handoff_summary or f"El lead requiere humano por {decision.intent}.",
                recommended_next_step=decision.recommended_next_step or "Tomar la conversacion y responder con diagnostico/cierre.",
                confidence=decision.confidence,
            )
            tool_results["handoff"] = handoff
        elif decision.needs_followup and lead_id:
            followup = self.tools.create_followup(
                lead_id=lead_id,
                note=decision.followup_note,
                minutes_from_now=decision.followup_minutes,
            )
            tool_results["followup"] = followup

        qualification = ai_qualification_from_message(message, decision.intent, self.qualification_min_score)
        if decision.handoff and qualification.get("status") == "observing":
            qualification["status"] = "needs_human"
            qualification["score"] = max(int(qualification.get("score") or 0), self.qualification_min_score)
            qualification["reason"] = decision.handoff_reason or qualification.get("reason") or "handoff solicitado"
        if lead_id:
            qualification_result = self.tools.submit_ai_qualification(lead_id, qualification)
            if not qualification_result.get("skipped"):
                tool_results["qualification"] = qualification_result

        self._remember(phone, message, decision.reply, {"intent": decision.intent, "mode": "claude"})
        return AgentReply(
            message=decision.reply,
            lead=lead if isinstance(lead, dict) else None,
            intent=decision.intent,
            handoff=decision.handoff or qualification.get("status") in {"qualified", "needs_human"},
            tool_results=tool_results,
        )

    def _decide(
        self,
        phone: str,
        message: str,
        lead: dict[str, Any] | None,
        products: list[dict[str, Any]],
        fallback_intent: str,
    ) -> BrainDecision:
        history = self.memory.load(phone)
        prompt = self._system_prompt(products)
        messages = self._messages(history, message, lead)
        try:
            raw = self.model.complete(prompt, messages, max_tokens=900) if self.model else ""
            return self._parse_decision(raw, fallback_intent)
        except (AnthropicClientError, ValueError, TypeError, KeyError):
            fallback = self.fallback_agent.handle_message(phone, message)
            return BrainDecision(
                reply=fallback.message,
                intent=fallback.intent,
                handoff=fallback.handoff,
                needs_followup=not fallback.handoff,
                followup_note="Fallback: seguimiento WhatsApp AI",
                stage="interesado" if fallback.intent in {"pricing", "interested"} else "conversacion",
                handoff_reason=f"Fallback WhatsApp AI: {fallback.intent}",
                handoff_trigger=fallback.intent,
                handoff_summary=f"El lead activo una entrega a humano por {fallback.intent}.",
                recommended_next_step="Tomar la conversacion, confirmar necesidad y guiar al siguiente paso.",
                confidence="medium",
            )

    def _system_prompt(self, products: list[dict[str, Any]]) -> str:
        product_lines = []
        for product in products[:8]:
            name = product.get("name") or product.get("title") or "Producto Club Commerce"
            price = product.get("price") or product.get("amount") or product.get("value") or product.get("closeValue")
            product_lines.append(f"- {name}: {price if price not in (None, '') else 'precio manual'}")
        catalog = "\n".join(product_lines) if product_lines else "No hay productos cargados para este mensaje."
        return (
            f"{SYSTEM_PROMPT}\n\n"
            "Debes responder SOLO JSON valido, sin markdown, con esta forma:\n"
            "{\n"
            '  "reply": "mensaje final para WhatsApp",\n'
            '  "intent": "discovery|pricing|interested|price_objection|time_objection|trust_objection|experience_question|ecommerce_general|shopify_question|meta_ads_question|meta_ads_lost_money|dropshipping_question|china_import_question|product_validation|brand_question|funnels_question|budget_capture|info_request|ready_for_handoff|needs_human",\n'
            '  "handoff": false,\n'
            '  "needsFollowUp": true,\n'
            '  "followUpNote": "nota interna breve",\n'
            '  "followUpMinutes": 1440,\n'
            '  "stage": "conversacion|interesado",\n'
            '  "handoffReason": "razon concreta para el closer si handoff=true",\n'
            '  "handoffTrigger": "buy_intent|human_request|payment|angry|strong_objection|high_intent|other",\n'
            '  "handoffSummary": "resumen corto del contexto para el closer",\n'
            '  "recommendedNextStep": "proximo paso sugerido para el closer",\n'
            '  "confidence": "low|medium|high"\n'
            "}\n\n"
            "Si el lead pide comprar, pagar, link, asesor, humano, o esta molesto: handoff=true.\n"
            "Si responde presupuesto, tienda, producto, ads o urgencia, incorporalo en tu diagnostico.\n"
            "Recomienda Academy/Pro/Elite solo si encaja con el caso y existe en el catalogo.\n"
            "No inventes precios. Usa solo este catalogo si hablas de precios:\n"
            f"{catalog}"
        )

    @staticmethod
    def _messages(
        history: list[dict[str, Any]],
        message: str,
        lead: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        formatted: list[dict[str, str]] = []
        for turn in history[-10:]:
            role = "assistant" if turn.get("role") == "assistant" else "user"
            content = str(turn.get("content") or "").strip()
            if content:
                formatted.append({"role": role, "content": content})
        if lead:
            formatted.append({"role": "user", "content": f"Contexto CRM del lead: {json.dumps(lead, ensure_ascii=True)}"})
        formatted.append({"role": "user", "content": message})
        return formatted[-12:]

    @staticmethod
    def _parse_decision(raw: str, fallback_intent: str) -> BrainDecision:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        data = json.loads(text)
        reply = str(data.get("reply") or "").strip()
        if not reply:
            raise ValueError("Claude decision missing reply")
        intent = str(data.get("intent") or fallback_intent).strip() or fallback_intent
        followup_minutes = data.get("followUpMinutes", 1440)
        try:
            followup_minutes = int(followup_minutes)
        except (TypeError, ValueError):
            followup_minutes = 1440
        followup_minutes = max(15, min(followup_minutes, 60 * 24 * 30))
        stage = str(data.get("stage") or "conversacion").strip()
        if stage not in {"conversacion", "interesado"}:
            stage = "conversacion"
        confidence = str(data.get("confidence") or "medium").strip().lower()
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"
        return BrainDecision(
            reply=reply,
            intent=intent,
            handoff=bool(data.get("handoff")),
            needs_followup=bool(data.get("needsFollowUp", True)),
            followup_note=str(data.get("followUpNote") or "Seguimiento WhatsApp AI").strip()[:240],
            followup_minutes=followup_minutes,
            stage=stage,
            handoff_reason=str(data.get("handoffReason") or "").strip()[:240],
            handoff_trigger=str(data.get("handoffTrigger") or intent).strip()[:120],
            handoff_summary=str(data.get("handoffSummary") or "").strip()[:500],
            recommended_next_step=str(data.get("recommendedNextStep") or "").strip()[:300],
            confidence=confidence,
        )

    @staticmethod
    def _should_load_products(message: str) -> bool:
        text = message.casefold()
        return any(
            word in text
            for word in (
                "precio",
                "cuanto",
                "cuánto",
                "plan",
                "planes",
                "programa",
                "academy",
                "pro",
                "elite",
                "pagar",
                "comprar",
                "shopify",
                "ads",
                "dropshipping",
                "china",
                "producto",
                "ecommerce",
            )
        )

    def _remember(self, phone: str, user_message: str, assistant_message: str, meta: dict[str, Any]) -> None:
        self.memory.append(phone, "user", user_message, meta=meta)
        self.memory.append(phone, "assistant", assistant_message, meta=meta)
