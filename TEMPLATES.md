# WhatsApp Templates

Foundation para enviar templates aprobados por Meta cuando la conversacion ya esta fuera de la ventana normal de 24 horas.

## Cuándo usar template vs mensaje normal

Usa mensaje normal (`/api/send-message`) cuando:

- El cliente escribio primero.
- La conversacion sigue dentro de la ventana de 24h iniciada por el cliente.
- Respondes manualmente desde CRM o el bot responde a un inbound reciente.

Usa template (`/api/send-template`) cuando:

- La ventana de 24h ya cerro.
- Necesitas reabrir la conversacion con un mensaje aprobado.
- El contacto tiene opt-in o base legal/operativa para recibir ese mensaje.

No uses templates para spam ni campañas masivas sin estrategia, aprobaciones y cumplimiento.

## Crear un template en Meta

1. Entra a Meta Business Manager.
2. Abre WhatsApp Manager.
3. Ve a `Message templates`.
4. Crea un template nuevo.
5. Elige categoria segun el caso:
   - Marketing: promocional o reactivacion comercial.
   - Utility: actualizaciones operativas.
   - Authentication: codigos/OTP.
6. Define:
   - Nombre en minúsculas y snake_case, por ejemplo `lead_followup_1`.
   - Idioma, por ejemplo `es`.
   - Body del mensaje.
   - Variables si aplica, por ejemplo `{{1}}`.
7. Envia a revision.

## Idioma para produccion

El agente responde al cliente siempre en espanol. Para el primer contacto automatico tambien usa un template aprobado en espanol:

```bash
AI_QUALIFICATION_LANGUAGE=es
```

Si Meta exige un codigo regional especifico en tu cuenta, usa el idioma exacto aprobado para el template, por ejemplo `es_LA` o `es_US`. Lo importante es que `AI_QUALIFICATION_TEMPLATE` exista aprobado en ese idioma.

## Esperar aprobación

- Meta puede aprobar, rechazar o pedir cambios.
- No intentes enviar templates no aprobados.
- Si se rechaza, ajusta el texto para que sea claro, no engañoso y no prometa resultados.

## Ejemplo hello_world

Meta incluye un template de prueba común:

```json
{
  "phone": "+13055550100",
  "templateName": "hello_world",
  "languageCode": "en_US",
  "components": []
}
```

`hello_world` sirve para pruebas tecnicas. Para produccion crea un template propio en espanol y configura `AI_QUALIFICATION_TEMPLATE` + `AI_QUALIFICATION_LANGUAGE` con los valores aprobados por Meta.

Endpoint:

```bash
curl -X POST "https://TU-AGENT.onrender.com/api/send-template" \
  -H "Content-Type: application/json" \
  -H "x-agent-api-key: $AGENT_API_KEY" \
  -d '{
    "phone": "+13055550100",
    "templateName": "hello_world",
    "languageCode": "en_US",
    "components": []
  }'
```

## Ejemplo con variable

Si tu template tiene una variable `{{1}}` en el body:

```json
{
  "phone": "+13055550100",
  "templateName": "lead_followup_1",
  "languageCode": "es",
  "components": [
    {
      "type": "body",
      "parameters": [
        {
          "type": "text",
          "text": "Adrian"
        }
      ]
    }
  ]
}
```

## Seguridad

- `AGENT_API_KEY` es obligatorio.
- El endpoint solo debe usarse con `WHATSAPP_PROVIDER=meta`.
- No hardcodees tokens.
- No loguees telefonos completos ni tokens.
- No uses templates para campañas masivas desde este foundation.

## Regla de ventana 24h

WhatsApp permite mensajes libres dentro de las 24h despues del ultimo mensaje iniciado por el cliente.
Fuera de esa ventana, debes usar un template aprobado por Meta.
