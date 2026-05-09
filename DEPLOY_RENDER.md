# Deploy Render — Club Commerce WhatsApp Agent

Guia para subir el agente a Render sin activar WhatsApp real hasta completar pruebas controladas.

## 1. Crear servicio

1. Entra a Render.
2. Selecciona `New Web Service`.
3. Conecta el repo del WhatsApp Agent.
4. Runtime: Python o Docker.
5. Si usas Docker, Render detectara el `Dockerfile`.

## 2. Build command

Si usas Python runtime:

```bash
pip install -r requirements.txt
```

Si usas Docker, no necesitas build command manual.

## 3. Start command

Si usas Python runtime:

```bash
uvicorn agent.main:app --host 0.0.0.0 --port $PORT
```

El `Procfile` y `Dockerfile` ya incluyen el mismo arranque.

## 4. Env vars

Configura estas variables en Render:

```bash
ENVIRONMENT=production
PORT=8000

CRM_API_URL=https://TU-CRM.com
CRM_API_KEY=secret_del_crm_bridge

ANTHROPIC_API_KEY=sk-ant...
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
AI_QUALIFICATION_MIN_SCORE=70
AI_QUALIFICATION_TEMPLATE=hello_world
AI_QUALIFICATION_LANGUAGE=es

WHATSAPP_PROVIDER=mock
META_ACCESS_TOKEN=
META_PHONE_NUMBER_ID=
META_VERIFY_TOKEN=token_privado_para_verify
META_APP_SECRET=
META_GRAPH_VERSION=v20.0

MEMORY_PATH=/app/data/agent_memory.json
```

Para el primer deploy usa:

```bash
WHATSAPP_PROVIDER=mock
```

Cambia a `meta` solo cuando vayas a conectar WhatsApp Cloud API.

## 5. Healthcheck

Health check path recomendado:

```text
/health
```

Prueba externa:

```bash
curl https://TU-BOT.onrender.com/health
```

Debe responder `ok: true`.

## 6. First live test

Antes de conectar Meta:

1. Abre `/health`.
2. Prueba `/simulate`:

```bash
curl -X POST https://TU-BOT.onrender.com/simulate \
  -H "Content-Type: application/json" \
  -d '{"phone":"+17865550100","name":"Dry Run","message":"Quiero informacion"}'
```

3. Confirma que el CRM reciba o actualice el lead.
4. Revisa logs y confirma que no haya tokens ni telefonos completos.

## 7. Webhook URL

Solo despues de pasar el first live test:

```text
https://TU-BOT.onrender.com/webhook
```

En Meta usa:

```text
Verify token: mismo valor de META_VERIFY_TOKEN
Subscribe field: messages
```

## 8. Prueba verify GET

```bash
curl "https://TU-BOT.onrender.com/webhook?hub.mode=subscribe&hub.verify_token=TU_VERIFY_TOKEN&hub.challenge=challenge-ok"
```

Debe responder:

```text
challenge-ok
```
