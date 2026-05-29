# AgentKit Deployment

Required env vars:
- `CRM_API_URL`
- `CRM_API_KEY`
- `AGENT_API_KEY`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`
- `WHATSAPP_PROVIDER`
- `META_ACCESS_TOKEN`
- `META_PHONE_NUMBER_ID`
- `META_VERIFY_TOKEN`
- `META_APP_SECRET`
- `META_GRAPH_VERSION`
- `MEMORY_PATH`
- `PORT`

Start:
```bash
uvicorn agent.main:app --host 0.0.0.0 --port $PORT
```

Health/debug:
- `/health`
- `/debug/status`
- `/debug/config`
- `/debug/automation-context`

Use mock provider for dry runs. Switch to Meta only after CRM diagnostics and template configuration are clean.
