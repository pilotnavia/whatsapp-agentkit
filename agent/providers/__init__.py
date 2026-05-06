"""WhatsApp provider factory."""

from __future__ import annotations

from typing import Any

from .base import IncomingMessage, WhatsAppProvider, WhatsAppProviderError
from .meta import MetaWhatsAppProvider
from .mock import MockWhatsAppProvider


def build_provider(settings: Any) -> WhatsAppProvider:
    provider = (getattr(settings, "whatsapp_provider", "") or "mock").lower()
    if provider == "meta":
        return MetaWhatsAppProvider(
            access_token=getattr(settings, "meta_access_token", ""),
            phone_number_id=getattr(settings, "meta_phone_number_id", ""),
            verify_token=getattr(settings, "meta_verify_token", ""),
            graph_version=getattr(settings, "meta_graph_version", "v20.0"),
        )
    return MockWhatsAppProvider(verify_token=getattr(settings, "meta_verify_token", "mock-verify"))


__all__ = [
    "IncomingMessage",
    "WhatsAppProvider",
    "WhatsAppProviderError",
    "MetaWhatsAppProvider",
    "MockWhatsAppProvider",
    "build_provider",
]

