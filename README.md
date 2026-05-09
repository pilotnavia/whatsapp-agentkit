# Club Commerce WhatsApp Agent

W2/W3/W4 crea un agente vendedor separado del CRM. W3 agrega Claude Brain opcional con memoria por telefono, usando fallback local si no hay `ANTHROPIC_API_KEY`. W4 prepara provider mock/meta para webhook real sin activar produccion.

## Variables necesarias

Copiar `.env.example` a `.env` y configurar localmente:

```bash
CRM_API_URL=http://127.0.0.1:4173
CRM_API_KEY=tu_api_key_del_crm_bridge
ANTHROPIC_API_KEY=tu_api_key_de_anthropic
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
AI_QUALIFICATION_MIN_SCORE=70
AI_QUALIFICATION_TEMPLATE=hello_world
AI_QUALIFICATION_LANGUAGE=es
WHATSAPP_PROVIDER=mock
META_ACCESS_TOKEN=
META_PHONE_NUMBER_ID=
META_VERIFY_TOKEN=agentkit-verify
META_APP_SECRET=
META_GRAPH_VERSION=v20.0
PORT=8000
MEMORY_PATH=./agent_memory.json
```

## Estructura

```text
agent/
  main.py          FastAPI mock server
  brain.py         Claude Brain + fallback local
  anthropic_client.py Cliente HTTP minimo para Anthropic Messages API
  memory.py        Memoria JSON por telefono
  crm_client.py    Cliente HTTP para W1 CRM Bridge
  tools.py         Tools del agente vendedor
  seller_agent.py  Logica local de ventas y handoff
  sales_prompt.py  Prompt y reglas del vendedor
  providers/       Mock provider y Meta WhatsApp Cloud API foundation
tests/
  test_local.py    Simulador sin WhatsApp real
```

## Validacion local

```bash
python3 -m py_compile agent/*.py
python3 -m py_compile agent/providers/*.py
python3 tests/test_local.py
```

## Ejecutar servidor mock

```bash
uvicorn agent.main:app --reload --port 8000
```

Smoke test local:

```bash
python3 scripts/smoke_test.py --local
```

Probar conversacion:

```bash
curl -X POST http://127.0.0.1:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"phone":"+17865550100","name":"Adrian Test","message":"Cuanto cuesta el programa?"}'
```

Webhook mock/meta:

```bash
# Verify webhook estilo Meta
curl "http://127.0.0.1:8000/webhook?hub.mode=subscribe&hub.verify_token=agentkit-verify&hub.challenge=ok"

# POST mock si WHATSAPP_PROVIDER=mock
curl -X POST http://127.0.0.1:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"phone":"+17865550100","name":"Adrian Test","message":"Quiero info"}'
```

## Docker local

```bash
docker build -t club-commerce-whatsapp-agent .
docker run --rm -p 8000:8000 \
  -e WHATSAPP_PROVIDER=mock \
  -e CRM_API_URL=http://host.docker.internal:4173 \
  -e CRM_API_KEY=tu_api_key_del_crm_bridge \
  club-commerce-whatsapp-agent
```

## Deploy env vars

Para Render/Railway usa las variables de `.env.example`. Minimo para produccion:

```bash
ENVIRONMENT=production
PORT=8000
CRM_API_URL=https://TU-CRM.com
CRM_API_KEY=secret_del_crm_bridge
ANTHROPIC_API_KEY=sk-ant...
WHATSAPP_PROVIDER=meta
META_ACCESS_TOKEN=token_meta
META_PHONE_NUMBER_ID=id_numero
META_VERIFY_TOKEN=verify_privado
META_APP_SECRET=app_secret
META_GRAPH_VERSION=v20.0
MEMORY_PATH=/app/data/agent_memory.json
```

Checklist completo:

```text
DEPLOY_CHECKLIST.md
```

Guias por plataforma:

```text
DEPLOY_RAILWAY.md
DEPLOY_RENDER.md
```

Start command de produccion:

```bash
uvicorn agent.main:app --host 0.0.0.0 --port $PORT
```

First live test recomendado:

1. Deploy con `WHATSAPP_PROVIDER=mock`.
2. Abrir `/health`.
3. Probar `/simulate`.
4. Confirmar lead en el CRM.
5. Cambiar a `WHATSAPP_PROVIDER=meta`.
6. Configurar Meta webhook en `/webhook`.

## W3/W4 pendientes

- Activar Meta Cloud API con credenciales reales.
- Agregar Twilio si se decide usarlo.
- Implementar human takeover operativo.
- Deploy y webhooks de produccion.

## Deploy seguro

Variables requeridas en produccion:

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

WHATSAPP_PROVIDER=meta
META_ACCESS_TOKEN=token_de_whatsapp_cloud_api
META_PHONE_NUMBER_ID=id_del_numero
META_VERIFY_TOKEN=token_para_verificar_webhook
META_APP_SECRET=app_secret_de_meta
META_GRAPH_VERSION=v20.0

MEMORY_PATH=/app/data/agent_memory.json
```

Healthcheck:

```bash
GET https://TU-BOT.com/health
```

Webhook en Meta:

```text
Callback URL: https://TU-BOT.com/webhook
Verify token: mismo valor de META_VERIFY_TOKEN
Campo: messages
```

Seguridad:

- `POST /webhook` exige `X-Hub-Signature-256` cuando `WHATSAPP_PROVIDER=meta`.
- La firma se valida con HMAC SHA256 usando `META_APP_SECRET`.
- No subas `.env` ni tokens al repo.
- Los logs/respuestas no deben mostrar tokens ni telefono completo.
