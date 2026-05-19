"""Provider interface for WhatsApp transports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class IncomingMessage:
    phone: str
    text: str
    name: str | None = None
    email: str | None = None
    provider_message_id: str | None = None
    raw: dict[str, Any] | None = None


class WhatsAppProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider_status: int | None = None,
        provider_code: str | int | None = None,
        provider_subcode: str | int | None = None,
        provider_message: str | None = None,
        provider_details: str | None = None,
        fbtrace_id: str | None = None,
    ):
        super().__init__(message)
        self.provider_status = provider_status
        self.provider_code = str(provider_code or "") if provider_code is not None else ""
        self.provider_subcode = str(provider_subcode or "") if provider_subcode is not None else ""
        self.provider_message = provider_message or message
        self.provider_details = provider_details or ""
        self.fbtrace_id = fbtrace_id or ""

    def safe_payload(self) -> dict[str, Any]:
        return {
            "providerStatus": self.provider_status,
            "providerCode": self.provider_code,
            "providerSubcode": self.provider_subcode,
            "providerMessage": self.provider_message,
            "providerDetails": self.provider_details,
            "fbtraceId": self.fbtrace_id,
        }


def provider_error_hint(exc: WhatsAppProviderError) -> str:
    text = " ".join([
        str(exc.provider_message or ""),
        str(exc.provider_details or ""),
        str(exc.provider_code or ""),
        str(exc.provider_subcode or ""),
    ]).lower()
    if str(exc.provider_code or "") == "190" or "authentication error" in text:
        return "META_ACCESS_TOKEN invalido o expirado. Genera un token nuevo/permanente y redeploy AgentKit."
    if "template" in text:
        return "Revisa que el template exista, este aprobado y tenga el idioma configurado."
    if "access token" in text or "token" in text or "oauth" in text:
        return "Revisa META_ACCESS_TOKEN."
    if "phone number" in text or "phone_number" in text or "recipient" in text:
        return "Revisa META_PHONE_NUMBER_ID o numero receptor permitido."
    if "allowed" in text or "allow list" in text or "test" in text:
        return "Agrega el recipient al test list o usa numero real en produccion."
    return "Revisa la configuracion de Meta WhatsApp y los permisos del numero."


class WhatsAppProvider(Protocol):
    name: str

    def send_message(self, phone: str, text: str) -> dict[str, Any]: ...

    def send_template(
        self,
        phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    def parse_webhook(self, payload: dict[str, Any]) -> IncomingMessage | None: ...

    def verify_webhook(self, request_or_query: Any) -> str | None: ...


def query_value(request_or_query: Any, key: str) -> str:
    if hasattr(request_or_query, "query_params"):
        return str(request_or_query.query_params.get(key, "")).strip()
    if isinstance(request_or_query, Mapping):
        return str(request_or_query.get(key, "")).strip()
    return ""
