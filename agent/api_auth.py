"""Small auth helpers shared by API endpoints and dependency-free tests."""

from __future__ import annotations

import secrets


def agent_api_key_valid(provided: str | None, expected: str | None) -> bool:
    provided_value = provided or ""
    expected_value = expected or ""
    return bool(expected_value and secrets.compare_digest(provided_value, expected_value))
