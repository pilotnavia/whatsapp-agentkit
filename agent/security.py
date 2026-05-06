"""Security helpers for inbound provider webhooks."""

from __future__ import annotations

import hashlib
import hmac


def sign_meta_payload(body: bytes, app_secret: str) -> str:
    digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_meta_signature(body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not body or not signature_header or not app_secret:
        return False
    signature = signature_header.strip()
    if not signature.startswith("sha256="):
        return False
    expected = sign_meta_payload(body, app_secret)
    return hmac.compare_digest(signature, expected)


def mask_phone(phone: str | None) -> str:
    clean = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(clean) <= 4:
        return "****"
    return f"***{clean[-4:]}"

