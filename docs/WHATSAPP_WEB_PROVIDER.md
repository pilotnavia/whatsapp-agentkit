# WhatsApp Web Session Provider

AgentKit can use the experimental `web_session` provider through the `whatsapp-web-bridge` sidecar. This lets the CRM connect existing WhatsApp / WhatsApp Business numbers by QR while AgentKit keeps the same send-message, send-template, inbound webhook, training-context, and human-takeover behavior.

Meta Cloud API remains available and is still the official provider. `web_session` is unofficial and should be treated as experimental. Use it for existing warm numbers, internal seller lines, or controlled agency operations, never for bulk outreach.

## Environment

```bash
WHATSAPP_PROVIDER=web_session
WEB_SESSION_BRIDGE_URL=https://wa-bridge.yourdomain.com
WEB_SESSION_BRIDGE_API_KEY=change_me_bridge_key
WEB_SESSION_DEFAULT_SESSION_ID=closer_1
AGENT_API_KEY=change_me_agent_key
```

For deployed services, `WEB_SESSION_BRIDGE_URL` must be reachable from AgentKit. If AgentKit runs on Render and the bridge runs locally, `http://localhost:3100` points to the AgentKit container, not your computer. Use a permanent Cloudflare Tunnel or deploy the bridge on a VPS.

## Supported Bridge Modes

| Mode | Recommended for | AgentKit requirement |
| --- | --- | --- |
| Local Bridge + Cloudflare Tunnel | Internal ClubCommerce use, small teams, 1-5 lines | `WEB_SESSION_BRIDGE_URL=https://wa-bridge.yourdomain.com` from the tunnel route |
| VPS Bridge + Docker | Clients, agencies, larger teams, production-style uptime | `WEB_SESSION_BRIDGE_URL=https://wa-bridge.yourdomain.com` from the VPS reverse proxy |

AgentKit does not need to know where the bridge is hosted. It only needs the public bridge URL and API key.

Local run example:

```bash
WHATSAPP_PROVIDER=web_session \
WEB_SESSION_BRIDGE_URL=http://127.0.0.1:3100 \
WEB_SESSION_BRIDGE_API_KEY=local_bridge_test \
WEB_SESSION_DEFAULT_SESSION_ID=closer_1 \
CRM_API_URL=http://127.0.0.1:4173 \
CRM_API_KEY=local_crm_test \
AGENT_API_KEY=local_agent_test \
python3 -m uvicorn agent.main:app --host 127.0.0.1 --port 8000
```

If local Python is 3.9 and Pydantic cannot evaluate `str | None`, install `eval_type_backport` or use Python 3.10+.

The bridge uses `AGENT_API_KEY` as a bearer token when posting inbound messages to:

```text
POST /webhooks/web-session
Authorization: Bearer AGENT_API_KEY
```

## Behavior

- `/api/send-message` sends freeform text through the configured bridge session.
- `/api/send-template` sends the CRM-rendered template text through the bridge session.
- Inbound bridge messages are parsed as normal WhatsApp inbound messages and go through the same human takeover and CRM transcript flow.
- If a conversation is in `human` or `handoff`, AgentKit does not auto-reply.
- CRM now manages line operations from `WhatsApp > Web Lines / QR`: create up to 20 sessions, assign closers, scan QR, monitor status, and deactivate a line.
- When CRM sends a message/template it can pass `metadata.sessionId`; AgentKit forwards that line choice to the bridge. If none is provided, AgentKit uses `WEB_SESSION_DEFAULT_SESSION_ID`.

## Limitations

- This is not the official Meta WhatsApp Cloud API.
- Official template status, template approval, and Meta billing do not apply to web sessions.
- Use low-volume controlled tests only.
- Keep opt-out, quiet hours, CRM queue limits, and human takeover enabled.
- Generate bridge keys with `openssl rand -hex 32`.
- Never commit `.env` files or log API keys.
