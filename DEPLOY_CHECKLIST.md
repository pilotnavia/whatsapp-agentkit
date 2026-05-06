# Production Dry Run Checklist

Checklist para subir el WhatsApp Agent de Club Commerce de forma controlada, sin exponer secretos.

## 1. Variables de entorno

Configura estas variables en Railway, Render o el proveedor que uses:

```bash
ENVIRONMENT=production
PORT=8000

CRM_API_URL=https://TU-CRM.com
CRM_API_KEY=secret_del_crm_bridge

ANTHROPIC_API_KEY=sk-ant...
ANTHROPIC_MODEL=claude-3-5-sonnet-latest

WHATSAPP_PROVIDER=meta
META_ACCESS_TOKEN=token_de_whatsapp_cloud_api
META_PHONE_NUMBER_ID=id_del_numero_de_whatsapp
META_VERIFY_TOKEN=token_privado_para_verify_get
META_APP_SECRET=app_secret_de_meta
META_GRAPH_VERSION=v20.0

MEMORY_PATH=/app/data/agent_memory.json
```

No subas `.env`, tokens, logs ni archivos de memoria al repo.

## 2. Deploy en Railway

1. Crear un nuevo proyecto en Railway.
2. Conectar el repo del bot.
3. Confirmar que detecta `Dockerfile` o Python app.
4. Agregar todas las variables de entorno.
5. Deploy.
6. Copiar la URL publica, por ejemplo:

```text
https://club-commerce-whatsapp-agent.up.railway.app
```

## 3. Deploy en Render

1. Crear `New Web Service`.
2. Conectar el repo del bot.
3. Build command:

```bash
pip install -r requirements.txt
```

4. Start command:

```bash
uvicorn agent.main:app --host 0.0.0.0 --port $PORT
```

5. Agregar todas las variables de entorno.
6. Deploy.

## 4. Healthcheck

```bash
curl https://TU-BOT.com/health
```

Debe responder algo como:

```json
{
  "ok": true,
  "service": "club-commerce-whatsapp-agent",
  "provider": "meta",
  "providerReady": true,
  "crmConfigured": true
}
```

## 5. Configurar Meta webhook

En Meta Developers:

1. App Dashboard.
2. WhatsApp > Configuration.
3. Callback URL:

```text
https://TU-BOT.com/webhook
```

4. Verify token:

```text
Mismo valor de META_VERIFY_TOKEN
```

5. Subscribe al campo:

```text
messages
```

## 6. Prueba verify GET

```bash
curl "https://TU-BOT.com/webhook?hub.mode=subscribe&hub.verify_token=TU_VERIFY_TOKEN&hub.challenge=challenge-ok"
```

Debe responder:

```text
challenge-ok
```

## 7. Prueba webhook POST con firma

Genera una firma local usando el mismo `META_APP_SECRET` y envia un payload de prueba. Ejemplo Python:

```bash
python3 - <<'PY'
import hashlib, hmac, json, os, urllib.request

url = "https://TU-BOT.com/webhook"
secret = os.environ["META_APP_SECRET"]
payload = {
  "entry": [{
    "changes": [{
      "value": {
        "contacts": [{"profile": {"name": "Dry Run Lead"}}],
        "messages": [{
          "from": "17865550100",
          "id": "wamid.dryrun",
          "type": "text",
          "text": {"body": "Quiero informacion"}
        }]
      }
    }]
  }]
}
body = json.dumps(payload).encode()
signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
req = urllib.request.Request(
  url,
  data=body,
  method="POST",
  headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
)
print(urllib.request.urlopen(req).read().decode())
PY
```

En produccion esta prueba puede intentar enviar respuesta por Meta si el provider esta configurado. Hazla solo cuando quieras validar el flujo real.

## 8. Prueba CRM Bridge

Con el CRM live:

```bash
curl -X POST "$CRM_API_URL/api/agent/leads/upsert" \
  -H "Content-Type: application/json" \
  -H "x-crm-api-key: $CRM_API_KEY" \
  -d '{"phone":"+17865550100","name":"Dry Run Lead","source":"WhatsApp","campaign":"WhatsApp AI Agent","notes":"Dry run CRM Bridge"}'
```

Debe devolver `ok: true` y un lead.

## 9. Smoke test del bot

Con el bot corriendo:

```bash
python3 scripts/smoke_test.py --base-url https://TU-BOT.com
```

Para local:

```bash
uvicorn agent.main:app --reload --port 8000
python3 scripts/smoke_test.py --local
```

## 10. Antes de activar trafico real

- Confirmar `/health`.
- Confirmar verify GET.
- Confirmar firma Meta POST.
- Confirmar CRM Bridge.
- Confirmar que el bot responde sin inventar precios.
- Confirmar handoff humano.
- Confirmar que `.env`, memoria y logs no estan versionados.

