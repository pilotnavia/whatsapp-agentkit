# Debugging AgentKit

Run local checks:
```bash
python3 -m py_compile agent/*.py agent/providers/*.py
python3 tests/test_local.py
```

Useful endpoints:
- `/health`: basic runtime status.
- `/debug/status`: provider, CRM, Claude and Meta configured flags.
- `/debug/automation-context`: confirms CRM training, automation, and Agent Tool registry cache.

Troubleshooting:
- `401` from CRM: check `CRM_API_KEY`.
- `403` from CRM agent endpoints: check Agent Tools in CRM; the corresponding tool may be disabled.
- `401` from `/api/send-template`: check `AGENT_API_KEY`.
- Meta code `190`: token invalid or expired.
- Template errors: verify provider template name, language code, approval status, and recipient permissions.

Never log tokens, full phone numbers, cookies, or auth headers.
