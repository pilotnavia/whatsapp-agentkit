# AgentKit Deployment

AgentKit is the WhatsApp/AI transport service. The CRM remains the source of truth for leads, Sales Training, templates, queue, safety rules, and AI Actions.

## Required Environment

- `PORT`
- `CRM_API_URL`
- `CRM_API_KEY`
- `AGENT_API_KEY`
- `WHATSAPP_PROVIDER=mock|meta|web_session`
- `MEMORY_PATH`

For Claude:

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`

For Meta WhatsApp Cloud API:

- `META_ACCESS_TOKEN`
- `META_PHONE_NUMBER_ID`
- `META_VERIFY_TOKEN`
- `META_APP_SECRET`
- `META_GRAPH_VERSION`

Qualification defaults:

- `AI_QUALIFICATION_MIN_SCORE`
- `AI_QUALIFICATION_TEMPLATE`
- `AI_QUALIFICATION_LANGUAGE`

Never commit real secrets.

## Local Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn agent.main:app --host 0.0.0.0 --port 8000
```

Checks:

```bash
python3 -m py_compile agent/*.py agent/providers/*.py
python3 tests/test_local.py
```

Useful local endpoints:

- `/health`
- `/readiness`
- `/debug/status`
- `/debug/config`
- `/debug/automation-context`
- `/simulate`

## Render

- Service type: Web Service
- Python version: Python 3.11 works with the included Dockerfile
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn agent.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/readiness`

## Experimental WhatsApp Web Provider

For controlled tests only:

```bash
WHATSAPP_PROVIDER=web_session
WEB_SESSION_BRIDGE_URL=https://your-bridge.example.com
WEB_SESSION_BRIDGE_API_KEY=...
WEB_SESSION_DEFAULT_SESSION_ID=closer_1
```

Start/deploy the separate `whatsapp-web-bridge` service first, then create and scan the session QR from CRM Settings > WhatsApp Providers.

`web_session` sends rendered text through WhatsApp Web. It is not the official Meta Cloud API and should not be used for bulk outreach.

`Procfile` and `Dockerfile` already use the same start command.

## Meta Webhook

Callback URL:

```text
https://AGENTKIT_DOMAIN/webhook
```

Meta GET verification:

- Meta sends `hub.verify_token`.
- It must match `META_VERIFY_TOKEN`.
- AgentKit returns the Meta challenge as plain text.

Meta POST messages:

- Subscribe the WhatsApp app to `messages`.
- AgentKit verifies `X-Hub-Signature-256` with `META_APP_SECRET` when using the Meta provider.
- AgentKit should return 200 for valid/ignored events to avoid retry storms.
- Use `META_PHONE_NUMBER_ID` from WhatsApp Phone Numbers, not the Business Account ID.

## Safe Live Test

1. Deploy CRM first and confirm `/api/health`.
2. Set AgentKit `CRM_API_URL` and `CRM_API_KEY`.
3. Deploy AgentKit with `WHATSAPP_PROVIDER=mock`.
4. Confirm `/readiness`.
5. Confirm CRM Settings > System Diagnostics > Test AgentKit.
6. Configure Meta env vars.
7. Switch `WHATSAPP_PROVIDER=meta`.
8. Verify Meta webhook GET.
9. Send one inbound test message from an allowed test recipient.
10. Confirm WhatsApp Inbox shows inbound/outbound transcript.
11. Test one approved template through CRM queue.

## Known Limitations

- AgentKit does not own scheduling. CRM queue/worker owns template scheduling and safety.
- `/readiness` checks CRM bridge endpoints but does not call Meta Graph API.
- Meta token validity is confirmed when a real send/webhook occurs.
