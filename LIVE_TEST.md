# Meta Live Test Controlado

Objetivo: conectar WhatsApp real con Meta para una prueba controlada, sin enviar campanas masivas.

Bot live:

```text
https://whatsapp-agentkit-4yl3.onrender.com
```

Webhook URL:

```text
https://whatsapp-agentkit-4yl3.onrender.com/webhook
```

## 1. Configurar variables en Render

En Render > servicio `whatsapp-agentkit` > Environment, configura:

```bash
WHATSAPP_PROVIDER=meta

CRM_API_URL=https://TU-CRM.com
CRM_API_KEY=secret_del_crm_bridge

ANTHROPIC_API_KEY=sk-ant...
ANTHROPIC_MODEL=claude-3-5-sonnet-latest

META_ACCESS_TOKEN=token_de_whatsapp_cloud_api
META_PHONE_NUMBER_ID=id_del_numero_de_whatsapp
META_VERIFY_TOKEN=token_privado_para_verify
META_APP_SECRET=app_secret_de_meta
META_GRAPH_VERSION=v20.0

MEMORY_PATH=/app/data/agent_memory.json
PORT=8000
```

No pegues estos valores en GitHub ni en capturas publicas.

## 2. Redeploy

1. Guarda las variables.
2. Ejecuta `Manual Deploy > Deploy latest commit`.
3. Espera que el deploy termine correctamente.

## 3. Revisar health y debug config

Health:

```bash
curl https://whatsapp-agentkit-4yl3.onrender.com/health
```

Debug sin secretos:

```bash
curl https://whatsapp-agentkit-4yl3.onrender.com/debug/config
```

Debe mostrar:

```json
{
  "ok": true,
  "provider": "meta",
  "crmConfigured": true,
  "claudeConfigured": true,
  "metaConfigured": true,
  "graphVersion": "v20.0"
}
```

Si `metaConfigured` es `false`, falta alguna de estas variables:

- `META_ACCESS_TOKEN`
- `META_PHONE_NUMBER_ID`
- `META_VERIFY_TOKEN`
- `META_APP_SECRET`

## 4. Configurar webhook en Meta

En Meta Developers:

1. Abre la app de WhatsApp.
2. Ve a `WhatsApp > Configuration` o `Webhooks`.
3. Callback URL:

```text
https://whatsapp-agentkit-4yl3.onrender.com/webhook
```

4. Verify token:

```text
Mismo valor de META_VERIFY_TOKEN
```

5. Click en Verify and Save.
6. Suscribe el campo:

```text
messages
```

## 5. Verificar GET webhook en Meta

Meta debe poder verificar el endpoint. Prueba manual:

```bash
curl "https://whatsapp-agentkit-4yl3.onrender.com/webhook?hub.mode=subscribe&hub.verify_token=TU_VERIFY_TOKEN&hub.challenge=challenge-ok"
```

Debe responder:

```text
challenge-ok
```

## 6. Enviar mensaje desde numero test

Usa solo un numero de prueba autorizado en Meta:

1. Desde el numero test, envia un mensaje sencillo:

```text
Hola, quiero informacion
```

2. Espera la respuesta del bot.
3. No lances broadcast ni campanas.
4. Prueba maximo 2-3 mensajes en esta fase.

## 7. Revisar CRM

En el CRM revisa:

- Lead creado o actualizado.
- Source: WhatsApp.
- Campaign: WhatsApp AI Agent.
- Activity registrada.
- Follow-up creado si aplica.
- Handoff si el mensaje fue de compra o humano.

## 8. Revisar logs

En Render revisa logs:

- No deben aparecer tokens.
- No deben aparecer telefonos completos.
- Errores de firma Meta deben responder 401.
- Errores de CRM deben responder 502.

## 9. Rollback a mock

Si algo falla, vuelve a modo seguro:

```bash
WHATSAPP_PROVIDER=mock
```

Luego:

1. Redeploy en Render.
2. Desactiva o pausa webhook en Meta si es necesario.
3. Verifica:

```bash
curl https://whatsapp-agentkit-4yl3.onrender.com/debug/config
```

Debe mostrar:

```json
{
  "provider": "mock"
}
```

## 10. Criterio de exito

La prueba live esta OK si:

- `/health` responde `ok: true`.
- `/debug/config` muestra `provider=meta` y `metaConfigured=true`.
- Meta verifica el webhook GET.
- El mensaje test llega al bot.
- El bot responde por WhatsApp.
- El lead aparece en CRM.
- La actividad aparece en CRM.
- No hubo envio masivo.

