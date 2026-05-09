# Deploy Railway — Club Commerce WhatsApp Agent

Guia para subir el agente a Railway sin enviar WhatsApp real hasta completar pruebas controladas.

## 1. Crear servicio

1. Entra a Railway.
2. Crea un nuevo proyecto.
3. Selecciona el repo del WhatsApp Agent.
4. Railway puede usar el `Dockerfile` incluido.
5. Confirma que el servicio quede como Web Service.

## 2. Start command

Si Railway no usa el Dockerfile automaticamente, configura:

```bash
uvicorn agent.main:app --host 0.0.0.0 --port $PORT
```

El `Dockerfile` ya usa:

```bash
uvicorn agent.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

## 3. Env vars

Configura estas variables en Railway:

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

Para la primera prueba deja:

```bash
WHATSAPP_PROVIDER=mock
```

Cambia a `meta` solo cuando vayas a conectar Meta Cloud API.

## 4. Healthcheck

Cuando Railway entregue una URL publica:

```bash
curl https://TU-BOT.up.railway.app/health
```

Debe responder `ok: true`.

## 5. First live test

Antes de conectar Meta:

1. Abre `/health`.
2. Prueba `/simulate`:

```bash
curl -X POST https://TU-BOT.up.railway.app/simulate \
  -H "Content-Type: application/json" \
  -d '{"phone":"+17865550100","name":"Dry Run","message":"Quiero informacion"}'
```

3. Confirma que el CRM reciba o actualice el lead.
4. Confirma que no hay tokens impresos en logs.

## 6. Webhook URL

Solo despues de pasar el first live test:

```text
https://TU-BOT.up.railway.app/webhook
```

En Meta usa:

```text
Verify token: mismo valor de META_VERIFY_TOKEN
Subscribe field: messages
```

## 7. Prueba verify GET

```bash
curl "https://TU-BOT.up.railway.app/webhook?hub.mode=subscribe&hub.verify_token=TU_VERIFY_TOKEN&hub.challenge=challenge-ok"
```

Debe responder:

```text
challenge-ok
```
