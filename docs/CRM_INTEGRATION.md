# CRM Integration

AgentKit connects to Club Commerce CRM through the CRM Bridge.

Required:
- `CRM_API_URL`
- `CRM_API_KEY`

AgentKit calls:
- `GET /api/agent/tools`
- `GET /api/agent/training-context`
- `GET /api/agent/whatsapp-automation`
- `POST /api/agent/leads/upsert`
- `POST /api/agent/activities`
- `POST /api/agent/sales-actions`
- `POST /api/agent/handoff`

CRM remains the source of truth. AgentKit should not schedule templates or bypass queue safety. It proposes sales actions and sends messages/templates only when CRM calls transport endpoints.

## Readiness

AgentKit exposes `GET /readiness` for deploy checks. It safely reports:
- provider and provider readiness
- CRM configuration and reachability
- `/api/agent/training-context` reachability
- `/api/agent/whatsapp-automation` reachability
- `/api/agent/tools` reachability
- Meta configuration flags
- Claude configuration flag
- warnings without secrets

CRM admins can call this indirectly from Settings > System Diagnostics > Test AgentKit.

## Agent Tool Registry

AgentKit reads `GET /api/agent/tools` with `x-crm-api-key` and caches the safe tool list briefly. The registry tells AgentKit which actions are enabled, disabled, high-risk, or approval-gated.

If a tool is disabled, AgentKit avoids proposing related AI sales actions. The CRM still enforces the registry as final authority, so disabled tools block actions even if AgentKit cache is stale.

Important tool keys:
- `read_training_context`
- `read_automation_context`
- `propose_sales_action`
- `request_handoff`
- `create_followup_task`
- `update_lead_safe_fields`
- `update_lead_custom_fields`
- `enroll_sequence`
- `enqueue_template`
- `pause_bot`

## Key Matching

Set these pairs to the same values:
- CRM `CRM_API_KEY` = AgentKit `CRM_API_KEY`
- CRM `AGENT_API_KEY` = AgentKit `AGENT_API_KEY`

`CRM_API_KEY` protects CRM bridge reads/writes. `AGENT_API_KEY` protects AgentKit send endpoints called by CRM.
