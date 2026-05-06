"""Production/local smoke test for the Club Commerce WhatsApp Agent."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20,
) -> dict[str, Any]:
    data = None
    req_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} unavailable: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{method} {url} returned invalid JSON") from exc


def smoke_health(base_url: str) -> dict[str, Any]:
    result = request_json("GET", f"{base_url}/health")
    if result.get("ok") is not True:
        raise RuntimeError("/health did not return ok=true")
    return result


def smoke_simulate(base_url: str) -> dict[str, Any]:
    result = request_json(
        "POST",
        f"{base_url}/simulate",
        {
            "phone": "+17865550100",
            "name": "Smoke Test",
            "message": "Quiero informacion de Club Commerce",
        },
    )
    if result.get("ok") is not True:
        raise RuntimeError("/simulate did not return ok=true")
    return result


def smoke_crm_bridge() -> dict[str, Any] | None:
    crm_url = os.getenv("CRM_API_URL", "").rstrip("/")
    crm_key = os.getenv("CRM_API_KEY", "")
    if not crm_url or not crm_key:
        return None
    return request_json(
        "POST",
        f"{crm_url}/api/agent/leads/upsert",
        {
            "phone": "+17865550100",
            "name": "Smoke Test CRM",
            "source": "WhatsApp",
            "campaign": "WhatsApp AI Agent",
            "notes": "Smoke test CRM Bridge",
        },
        headers={"x-crm-api-key": crm_key},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test Club Commerce WhatsApp Agent")
    parser.add_argument("--base-url", default="", help="Agent base URL, example: https://bot.example.com")
    parser.add_argument("--local", action="store_true", help="Use http://127.0.0.1:8000")
    parser.add_argument("--skip-simulate", action="store_true", help="Only test /health and optional CRM bridge")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = "http://127.0.0.1:8000" if args.local else args.base_url.strip()
    if not base_url:
        print("ERROR: pass --local or --base-url https://TU-BOT.com", file=sys.stderr)
        return 2
    base_url = base_url.rstrip("/")

    print(f"Testing agent: {base_url}")
    health = smoke_health(base_url)
    print(f"health OK provider={health.get('provider')} crmConfigured={health.get('crmConfigured')}")

    if not args.skip_simulate:
        simulate = smoke_simulate(base_url)
        print(f"simulate OK intent={simulate.get('intent')} handoff={simulate.get('handoff')}")

    crm = smoke_crm_bridge()
    if crm is None:
        print("crm bridge skipped: CRM_API_URL/CRM_API_KEY not set")
    else:
        print(f"crm bridge OK created={crm.get('created')} leadId={(crm.get('lead') or {}).get('id')}")

    print("Smoke test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

