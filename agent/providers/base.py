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
    pass


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
