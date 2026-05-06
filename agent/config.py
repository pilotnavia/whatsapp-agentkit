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
    anthropic_model: str
    whatsapp_provider: str
    environment: str
    port: int
    agent_name: str
    business_name: str
    memory_path: str
    meta_access_token: str
    meta_phone_number_id: str
    meta_verify_token: str
    meta_app_secret: str
    meta_graph_version: str

    @property
    def crm_ready(self) -> bool:
        return bool(self.crm_api_url and self.crm_api_key)

    @property
    def whatsapp_ready(self) -> bool:
        if self.whatsapp_provider == "meta":
            return bool(
                self.meta_access_token
                and self.meta_phone_number_id
                and self.meta_verify_token
                and self.meta_app_secret
            )
        return True


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
        anthropic_model=_env("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
        whatsapp_provider=_env("WHATSAPP_PROVIDER", "mock").lower(),
        environment=_env("ENVIRONMENT", "development"),
        port=port,
        agent_name=_env("AGENT_NAME", "Club Commerce AI"),
        business_name=_env("BUSINESS_NAME", "Club Commerce"),
        memory_path=_env("MEMORY_PATH", "./agent_memory.json"),
        meta_access_token=_env("META_ACCESS_TOKEN"),
        meta_phone_number_id=_env("META_PHONE_NUMBER_ID"),
        meta_verify_token=_env("META_VERIFY_TOKEN", "agentkit-verify"),
        meta_app_secret=_env("META_APP_SECRET"),
        meta_graph_version=_env("META_GRAPH_VERSION", "v20.0"),
    )
