"""Environment-driven settings for the WhatsApp sales agent."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    crm_api_url: str
    crm_api_key: str
    anthropic_api_key: str
    whatsapp_provider: str
    environment: str
    port: int
    agent_name: str
    business_name: str

    @property
    def crm_ready(self) -> bool:
        return bool(self.crm_api_url and self.crm_api_key)


def load_settings() -> Settings:
    port_raw = _env("PORT", "8000")
    try:
        port = int(port_raw)
    except ValueError:
        port = 8000

    return Settings(
        crm_api_url=_env("CRM_API_URL", "http://127.0.0.1:4173").rstrip("/"),
        crm_api_key=_env("CRM_API_KEY"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        whatsapp_provider=_env("WHATSAPP_PROVIDER", "mock").lower(),
        environment=_env("ENVIRONMENT", "development"),
        port=port,
        agent_name=_env("AGENT_NAME", "Club Commerce AI"),
        business_name=_env("BUSINESS_NAME", "Club Commerce"),
    )

