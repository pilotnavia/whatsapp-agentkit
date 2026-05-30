# Debugging AgentKit

Run local checks:
```bash
python3 -m py_compile agent/*.py agent/providers/*.py
python3 tests/test_local.py
```

Useful endpoints:
- `/health`: basic runtime status.
- `/readiness`: deploy readiness for CRM bridge, Agent Tools, Meta env vars, and Claude config.
- `/debug/status`: provider, CRM, Claude and Meta configured flags.
- `/debug/automation-context`: confirms CRM training, automation, and Agent Tool registry cache.

Troubleshooting:
- `401` from CRM: check `CRM_API_KEY`.
- `403` from CRM agent endpoints: check Agent Tools in CRM; the corresponding tool may be disabled.
- `401` from `/api/send-template`: check `AGENT_API_KEY`.
- Meta code `190`: token invalid or expired.
- Template errors: verify provider template name, language code, approval status, and recipient permissions.
- `/readiness` says CRM context unreachable: confirm CRM public URL, `CRM_API_KEY`, and CRM `/api/health`.
- `/readiness` says Meta configured false: confirm `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID`, `META_VERIFY_TOKEN`, and `META_APP_SECRET`.
- Webhook GET fails: confirm callback URL is `https://AGENTKIT_DOMAIN/webhook` and verify token matches `META_VERIFY_TOKEN`.
- Webhook POST returns 401: confirm Meta app secret signature is present/valid when using provider `meta`.

Never log tokens, full phone numbers, cookies, or auth headers.
