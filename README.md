# Club Commerce WhatsApp Agent

W2/W3 crea un agente vendedor separado del CRM. Todavia no conecta WhatsApp real; W3 agrega Claude Brain opcional con memoria por telefono, usando fallback local si no hay `ANTHROPIC_API_KEY`.

## Variables necesarias

Copiar `.env.example` a `.env` y configurar localmente:

```bash
CRM_API_URL=http://127.0.0.1:4173
CRM_API_KEY=tu_api_key_del_crm_bridge
ANTHROPIC_API_KEY=tu_api_key_de_anthropic
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
WHATSAPP_PROVIDER=mock
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
tests/
  test_local.py    Simulador sin WhatsApp real
```

## Validacion local

```bash
python3 -m py_compile agent/*.py
python3 tests/test_local.py
```

## Ejecutar servidor mock

```bash
uvicorn agent.main:app --reload --port 8000
```

Probar conversacion:

```bash
curl -X POST http://127.0.0.1:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"phone":"+17865550100","name":"Adrian Test","message":"Cuanto cuesta el programa?"}'
```

## W3/W4 pendientes

- Agregar proveedor WhatsApp real: Meta Cloud API o Twilio.
- Implementar human takeover operativo.
- Deploy y webhooks de produccion.
