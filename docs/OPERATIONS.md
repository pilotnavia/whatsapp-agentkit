# AgentKit Operations

AgentKit is the WhatsApp/AI transport service. The CRM remains the source of truth for leads, Sales Training, templates, automation, and approved AI actions.

Do not place secrets in docs, screenshots, or logs. Use configured/reachable flags from `/readiness`.

## Daily Checks

```bash
curl https://whatsapp-agentkit-4yl3.onrender.com/health
curl https://whatsapp-agentkit-4yl3.onrender.com/readiness
```

Expected readiness for `web_session` operations:

- `provider = web_session`
- `crmReachable = true`
- `trainingContextReachable = true`
- `automationContextReachable = true`
- `agentToolsReachable = true`
- `webSessionBridgeConfigured = true`
- `webSessionDefaultSessionConfigured = true`
- `webSessionBridgeReachable = true`

Expected readiness for Meta operations:

- provider is `meta`
- Meta environment flags are configured
- CRM context endpoints are reachable
- Claude/mock model configuration is intentional

## Environment Inventory

Required for CRM integration:

| Variable | Sensitive | Notes |
| --- | --- | --- |
| `CRM_API_URL` | no | Public CRM URL. |
| `CRM_API_KEY` | yes | Must match CRM `CRM_API_KEY`. |
| `AGENT_API_KEY` | yes | Must match CRM `AGENT_API_KEY` and bridge `AGENTKIT_API_KEY` where applicable. |

Provider:

| Variable | Sensitive | Notes |
| --- | --- | --- |
| `WHATSAPP_PROVIDER` | no | `mock`, `meta`, or `web_session`. |
| `WEB_SESSION_BRIDGE_URL` | no | Required for `web_session`; must be public from Render. |
| `WEB_SESSION_BRIDGE_API_KEY` | yes | Required for `web_session`; matches bridge `BRIDGE_API_KEY`. |
| `WEB_SESSION_DEFAULT_SESSION_ID` | no | Default connected bridge session. |
| `META_ACCESS_TOKEN` | yes | Required for Meta provider. |
| `META_PHONE_NUMBER_ID` | yes-ish | Treat as sensitive operational config. |
| `META_VERIFY_TOKEN` | yes | Webhook verification. |
| `META_APP_SECRET` | yes | Meta webhook signature validation. |

AI/model:

| Variable | Sensitive | Notes |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | yes | If Claude live mode is enabled. |
| model/config variables | no/yes | Keep provider-specific secrets out of logs. |

## CRM Context Dependencies

AgentKit should be able to fetch:

- `GET /api/agent/training-context`
- `GET /api/agent/whatsapp-automation`
- `GET /api/agent/tools`

If one of these fails, AgentKit should continue safely with fallback behavior, but production AI quality may degrade.

## Bridge Troubleshooting

If `/readiness` reports `webSessionBridgeReachable=false`:

1. Confirm public bridge health from a separate network.
2. Confirm `WEB_SESSION_BRIDGE_URL` is not `localhost` in Render.
3. Confirm `WEB_SESSION_BRIDGE_API_KEY` matches bridge `BRIDGE_API_KEY`.
4. Confirm bridge `/sessions` without auth returns `401`.
5. Confirm bridge `/sessions` with auth returns a connected `WEB_SESSION_DEFAULT_SESSION_ID`.

## Safe Live Test

Do not bulk send from AgentKit. For live verification:

1. Use a confirmed consenting recipient.
2. Send one CRM manual message or approved template.
3. Confirm CRM message store, AgentKit logs, bridge provider, and recipient receipt.
4. Confirm inbound reply path separately.
5. Stop after one controlled message unless a human approves another test.

## Rollback

If AgentKit deploy breaks:

1. Redeploy previous known-good commit on Render.
2. Confirm `/health`.
3. Confirm `/readiness`.
4. Confirm CRM `POST /api/admin/test-agentkit`.
5. Avoid live sends until readiness is clean.
