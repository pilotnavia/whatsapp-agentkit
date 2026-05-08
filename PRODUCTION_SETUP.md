# Production Setup - WhatsApp Agent

Checklist para dejar el agente operando con token permanente de Meta y rollback rapido.

## 1. Crear System User en Meta Business

1. Entra a Meta Business Settings.
2. Ve a `Users > System users`.
3. Crea un System User con nombre tipo `Club Commerce WhatsApp Agent`.
4. Selecciona rol `Admin` si necesitas control completo del WhatsApp Business Account.
5. Guarda el System User ID.

## 2. Asignar permisos WhatsApp

1. En el System User, abre `Assigned assets`.
2. Asigna el WhatsApp Business Account usado por Club Commerce.
3. Asigna el phone number de WhatsApp Cloud API.
4. Asigna la app Meta conectada al webhook.
5. Permisos recomendados para el token:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
   - `business_management` si Meta lo exige para listar/operar assets
6. Evita permisos no usados por el agente.

## 3. Generar token permanente

1. En el System User, pulsa `Generate token`.
2. Selecciona la app correcta.
3. Marca los permisos de WhatsApp.
4. Genera el token.
5. Copialo una sola vez y guardalo en un password manager.
6. No lo pegues en GitHub, logs, screenshots ni chats publicos.

## 4. Reemplazar token temporal en Render

En Render, abre el servicio `whatsapp-agentkit` y ve a `Environment`.

Configura o actualiza:

```env
WHATSAPP_PROVIDER=meta
META_ACCESS_TOKEN=TOKEN_PERMANENTE_DEL_SYSTEM_USER
META_PHONE_NUMBER_ID=TU_PHONE_NUMBER_ID
META_VERIFY_TOKEN=TU_VERIFY_TOKEN
META_APP_SECRET=TU_APP_SECRET
META_GRAPH_VERSION=v20.0
CRM_API_URL=https://TU-CRM.onrender.com
CRM_API_KEY=TU_CRM_API_KEY
ANTHROPIC_API_KEY=TU_ANTHROPIC_API_KEY
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
AGENT_API_KEY=TU_AGENT_API_KEY
MEMORY_PATH=/tmp/agent_memory.json
```

Luego ejecuta `Manual Deploy > Deploy latest commit`.

## 5. Verificar estado sin secretos

Abre:

```bash
curl https://TU-AGENT.onrender.com/health
curl https://TU-AGENT.onrender.com/debug/config
curl https://TU-AGENT.onrender.com/debug/status
```

Esperado:

- `provider` = `meta`
- `crmConfigured` = `true`
- `metaConfigured` = `true`
- `claudeConfigured` = `true` si Anthropic esta configurado
- `uptime` mayor que `0`
- `commit` con hash si Render expone `RENDER_GIT_COMMIT`

## 6. Probar mensaje real controlado

1. En Meta Developers, confirma que el webhook apunta a:

```text
https://TU-AGENT.onrender.com/webhook
```

2. Confirma que el campo `messages` esta suscrito.
3. Envia un mensaje desde un numero test autorizado.
4. Revisa logs de Render. Debes ver logs seguros como:
   - `POST /webhook received`
   - `POST /webhook payload summary`
   - `POST /webhook message processed`
   - `POST /webhook send success`
5. Revisa el CRM:
   - lead creado/actualizado
   - intake/contexto actualizado
   - activity registrada
   - handoff si aplica

## 7. Rollback rapido a mock

Si algo se comporta raro:

1. En Render cambia:

```env
WHATSAPP_PROVIDER=mock
```

2. Redeploy.
3. Confirma:

```bash
curl https://TU-AGENT.onrender.com/debug/status
```

4. El webhook seguira vivo, pero el agente no intentara usar Meta provider real.

## 8. Seguridad operativa

- Nunca imprimas `META_ACCESS_TOKEN`, `META_APP_SECRET`, `CRM_API_KEY`, `AGENT_API_KEY` ni `ANTHROPIC_API_KEY`.
- Rota tokens si se pegan por error en screenshots, logs o chats.
- Mantén `WHATSAPP_PROVIDER=mock` para pruebas que no sean live.
- Usa mensajes test antes de conectar trafico real.
- No uses este agente para campanas masivas sin templates aprobados y opt-in.
