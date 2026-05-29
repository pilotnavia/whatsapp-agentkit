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
