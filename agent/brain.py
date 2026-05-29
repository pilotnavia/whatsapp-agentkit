"""Claude-powered sales brain that coordinates CRM tools and memory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from .anthropic_client import AnthropicClientError
from .memory import ConversationMemory
from .sales_prompt import SYSTEM_PROMPT
from .seller_agent import AgentReply, ClubCommerceSellerAgent, _detect_intent
from .tools import CRMSalesTools, ai_qualification_from_message, utc_in


ENGLISH_REPLY_MARKERS = (
    "how can i",
    "i can help",
    "what is your",
    "do you have",
    "let me",
    "sure,",
    "would you",
    "tell me",
    "are you",
)

SPANISH_REPLY_MARKERS = (
    "tienda",
    "producto",
    "presupuesto",
    "equipo",
    "asesor",
    "ayudo",
    "quieres",
    "tienes",
    "empezando",
    "ventas",
    "programa",
    "precio",
    "claro",
)


def active_training_products(training_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(training_context, dict):
        return []
    products = training_context.get("activeProducts") or []
    return products if isinstance(products, list) else []


def training_ai_rules(training_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(training_context, dict):
        return {}
    rules = training_context.get("aiRules") or {}
    return rules if isinstance(rules, dict) else {}


def matches_opt_out(message: str, training_context: dict[str, Any] | None) -> bool:
    rules = training_ai_rules(training_context)
    keywords = rules.get("optOutKeywords") if isinstance(rules.get("optOutKeywords"), list) else []
    if not keywords:
        keywords = ["stop", "cancelar", "no me escribas", "salir", "unsubscribe"]
    text = message.casefold()
    return any(str(keyword or "").strip().casefold() in text for keyword in keywords if str(keyword or "").strip())


def looks_like_english_customer_reply(reply: str) -> bool:
    lowered = reply.casefold()
    english_hits = sum(1 for marker in ENGLISH_REPLY_MARKERS if marker in lowered)
    spanish_hits = sum(1 for marker in SPANISH_REPLY_MARKERS if marker in lowered)
    return english_hits >= 2 and spanish_hits == 0


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
        training_context = self.tools.get_training_context()
        automation_context = self.tools.get_whatsapp_automation() if hasattr(self.tools, "get_whatsapp_automation") else {}
        agent_tools_context = self.tools.get_agent_tools() if hasattr(self.tools, "get_agent_tools") else {}
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

        if matches_opt_out(message, training_context):
            reply_text = "Listo, no te enviaremos mas mensajes automaticos. Si necesitas ayuda luego, puedes escribirnos por aqui."
            self.tools.log_activity(
                "Lead solicito opt-out por WhatsApp",
                lead_id=lead_id,
                activity_type="whatsapp_opt_out",
                meta={"channel": "whatsapp", "sender": "system", "messagePreview": message[:180]},
            )
            self._remember(phone, message, reply_text, {"intent": "opt_out", "mode": "claude"})
            return AgentReply(reply_text, lead if isinstance(lead, dict) else None, "opt_out", handoff=False, tool_results={"upsert": upsert})

        rules = training_ai_rules(training_context)
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
            reply_text = "Gracias por escribirnos. Un asesor del equipo te respondera personalmente por aqui."
            self._remember(phone, message, reply_text, {"intent": "auto_reply_disabled", "mode": "claude"})
            return AgentReply(reply_text, lead if isinstance(lead, dict) else None, "auto_reply_disabled", handoff=True, tool_results={"upsert": upsert, "handoff": handoff})

        training_products = active_training_products(training_context)
        products = training_products or (self.tools.get_products() if self._should_load_products(message) else [])
        decision = self._decide(phone, message, lead, products, inferred_intent, training_context, automation_context, agent_tools_context)

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
            sales_action = self._propose_sales_action(
                lead_id=lead_id,
                phone=phone,
                message=message,
                decision=decision,
                qualification=qualification,
                automation_context=automation_context,
            )
            if sales_action and not sales_action.get("skipped"):
                tool_results["salesAction"] = sales_action

        self._remember(phone, message, decision.reply, {"intent": decision.intent, "mode": "claude"})
        return AgentReply(
            message=decision.reply,
            lead=lead if isinstance(lead, dict) else None,
            intent=decision.intent,
            handoff=decision.handoff or qualification.get("status") in {"qualified", "needs_human"},
            tool_results=tool_results,
	        )

    def _automation_template_id(self, automation_context: dict[str, Any], *needles: str) -> str:
        templates = automation_context.get("templates") if isinstance(automation_context, dict) else []
        if not isinstance(templates, list):
            return ""
        normalized_needles = [needle.lower() for needle in needles if needle]
        for template in templates:
            haystack = " ".join(
                str(template.get(key) or "")
                for key in ("id", "name", "label", "category", "providerTemplateName")
            ).lower()
            haystack += " " + " ".join(str(tag).lower() for tag in template.get("tags", []) if isinstance(tag, str))
            if all(needle in haystack for needle in normalized_needles):
                return str(template.get("id") or "")
        for template in templates:
            if template.get("status") == "active":
                return str(template.get("id") or "")
        return ""

    def _automation_sequence_id(self, automation_context: dict[str, Any]) -> str:
        sequences = automation_context.get("sequences") if isinstance(automation_context, dict) else []
        if not isinstance(sequences, list):
            return ""
        for sequence in sequences:
            if sequence.get("status") == "active":
                return str(sequence.get("id") or "")
        return ""

    def _propose_sales_action(
        self,
        lead_id: str,
        phone: str,
        message: str,
        decision: ClaudeDecision,
        qualification: dict[str, Any],
        automation_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not hasattr(self.tools, "propose_sales_action"):
            return None
        metadata = {
            "intent": decision.intent,
            "score": qualification.get("score"),
            "urgency": qualification.get("urgency"),
            "objection": qualification.get("objection"),
            "recommendedProduct": qualification.get("recommendedProduct"),
            "nextBestAction": decision.recommended_next_step or decision.followup_note,
        }
        if decision.handoff or decision.intent in {"ready_for_handoff", "needs_human"}:
            return self.tools.propose_sales_action(
                lead_id=lead_id,
                phone=phone,
                action_type="request_handoff",
                priority="high",
                title="Lead listo para humano",
                reasoning=decision.handoff_reason or "El lead mostro intencion fuerte o pidio humano.",
                recommended_message=decision.handoff_summary or message[:500],
                metadata=metadata,
            )
        if decision.intent in {"pricing", "price_objection"}:
            template_id = self._automation_template_id(automation_context, "price") or self._automation_template_id(automation_context, "precio")
            return self.tools.propose_sales_action(
                lead_id=lead_id,
                phone=phone,
                action_type="send_template" if template_id else "create_followup",
                priority="medium",
                title="Seguimiento por precio",
                reasoning="El lead pregunto precio o mostro objecion de presupuesto.",
                recommended_message=decision.reply,
                template_id=template_id,
                follow_up_at=utc_in(60),
                metadata=metadata,
            )
        if decision.intent in {"interested", "budget_capture", "info_request"}:
            sequence_id = self._automation_sequence_id(automation_context)
            return self.tools.propose_sales_action(
                lead_id=lead_id,
                phone=phone,
                action_type="enroll_sequence" if sequence_id else "create_followup",
                priority="medium",
                title="Nutrir lead interesado",
                reasoning="El lead mostro interes y puede necesitar seguimiento controlado.",
                recommended_message=decision.reply,
                sequence_id=sequence_id,
                follow_up_at=utc_in(120),
                metadata=metadata,
            )
        if qualification.get("budget") or qualification.get("urgency"):
            return self.tools.propose_sales_action(
                lead_id=lead_id,
                phone=phone,
                action_type="update_lead",
                priority="low",
                title="Actualizar contexto comercial",
                reasoning="El lead compartio presupuesto, urgencia o contexto util para el closer.",
                lead_patch={"followUpNote": decision.followup_note},
                metadata=metadata,
            )
        return None

    def _decide(
        self,
        phone: str,
        message: str,
        lead: dict[str, Any] | None,
        products: list[dict[str, Any]],
        fallback_intent: str,
        training_context: dict[str, Any] | None = None,
        automation_context: dict[str, Any] | None = None,
        agent_tools_context: dict[str, Any] | None = None,
    ) -> BrainDecision:
        history = self.memory.load(phone)
        prompt = self._system_prompt(products, training_context, automation_context, agent_tools_context)
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

    def _system_prompt(
        self,
        products: list[dict[str, Any]],
        training_context: dict[str, Any] | None = None,
        automation_context: dict[str, Any] | None = None,
        agent_tools_context: dict[str, Any] | None = None,
    ) -> str:
        product_lines = []
        for product in products[:8]:
            name = product.get("name") or product.get("title") or "Producto Club Commerce"
            price = product.get("price") or product.get("amount") or product.get("value") or product.get("closeValue")
            description = product.get("shortDescription") or product.get("type") or ""
            product_lines.append(f"- {name}: {price if price not in (None, '') else 'precio manual'} {description}".strip())
        catalog = "\n".join(product_lines) if product_lines else "No hay productos cargados para este mensaje."
        training_context = training_context if isinstance(training_context, dict) else {}
        business = training_context.get("businessProfile") if isinstance(training_context.get("businessProfile"), dict) else {}
        faqs = training_context.get("activeFaqs") if isinstance(training_context.get("activeFaqs"), list) else []
        objections = training_context.get("activeObjections") if isinstance(training_context.get("activeObjections"), list) else []
        playbooks = training_context.get("activePlaybooks") if isinstance(training_context.get("activePlaybooks"), list) else []
        rules = training_ai_rules(training_context)
        language = business.get("defaultLanguage") or "es"
        automation_context = automation_context if isinstance(automation_context, dict) else {}
        templates = automation_context.get("templates") if isinstance(automation_context.get("templates"), list) else []
        sequences = automation_context.get("sequences") if isinstance(automation_context.get("sequences"), list) else []
        automation_settings = automation_context.get("settings") if isinstance(automation_context.get("settings"), dict) else {}
        agent_tools_context = agent_tools_context if isinstance(agent_tools_context, dict) else {}
        agent_tools = agent_tools_context.get("tools") if isinstance(agent_tools_context.get("tools"), list) else []
        training_summary = json.dumps(
            {
                "businessProfile": business,
                "faqs": faqs[:8],
                "objections": objections[:8],
                "playbooks": playbooks[:6],
                "aiRules": rules,
            },
            ensure_ascii=True,
        )[:8000]
        automation_summary = json.dumps(
            {
                "templates": templates[:10],
                "sequences": sequences[:6],
                "settings": automation_settings,
            },
            ensure_ascii=True,
        )[:4000]
        agent_tools_summary = json.dumps(
            {
                "enabledTools": [tool for tool in agent_tools if isinstance(tool, dict) and tool.get("status") == "enabled"],
                "disabledTools": [tool.get("key") for tool in agent_tools if isinstance(tool, dict) and tool.get("status") != "enabled"],
            },
            ensure_ascii=True,
        )[:3000]
        return (
            f"{SYSTEM_PROMPT}\n\n"
            "CONTEXTO EDITABLE DEL CRM:\n"
            f"{training_summary}\n\n"
            "CONTEXTO DE WHATSAPP AUTOMATION DEL CRM:\n"
            f"{automation_summary}\n"
            "- El CRM es dueño de programar y enviar templates. NO digas que ya enviaste un template.\n"
            "- Puedes usar esta info solo como contexto interno sobre follow-ups aprobados y reglas de seguridad.\n\n"
            "AGENT TOOL REGISTRY DEL CRM:\n"
            f"{agent_tools_summary}\n"
            "- No propongas acciones cuyo tool key aparezca en disabledTools.\n"
            "- El CRM bloquea cualquier accion deshabilitada aunque la propongas.\n\n"
            "IDIOMA OBLIGATORIO:\n"
            f"- Idioma base configurado por el CRM: {language}. Si no es claro, responde en espanol.\n"
            "- El campo reply debe estar SIEMPRE en espanol salvo que el CRM indique otro idioma por default.\n"
            "- Si el lead escribe en ingles, entiende la intencion y responde en espanol amable.\n"
            "- No uses Spanglish salvo nombres tecnicos inevitables: Shopify, Meta Ads, dropshipping.\n"
            "- Maximo 2-5 lineas y una sola pregunta de calificacion a la vez.\n\n"
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
            "Tambien usa handoffTriggers del CRM para decidir handoff.\n"
            "Si requireHumanApproval=true, califica con cuidado y entrega a humano antes de cerrar agresivamente.\n"
            "Si detectas optOutKeywords, confirma baja y no continues venta.\n"
            "Si responde presupuesto, tienda, producto, ads o urgencia, incorporalo en tu diagnostico.\n"
            "Recomienda productos solo si encajan y existen en el catalogo CRM.\n"
            "No inventes precios, garantias, descuentos ni promesas. Usa solo este catalogo si hablas de precios:\n"
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
        if looks_like_english_customer_reply(reply):
            raise ValueError("Claude decision reply must be Spanish")
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
