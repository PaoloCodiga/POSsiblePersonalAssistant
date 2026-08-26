# n8n

Future flow: Email / Teams / Telegram / WhatsApp / Plaud → n8n → future PPA Gateway / AI → PPA Odoo API. No production workflows are included in Phase 1.
# Plaud development workflow

Import `workflows/plaud-meeting-ingestion.json` into n8n. It receives Zapier at `POST /webhook/ppa/plaud`, checks `X-PPA-N8N-Webhook-Secret`, normalizes the adapter payload, and calls PPA internally at `PPA_INTERNAL_BASE_URL` with `PPA_API_KEY`. Do not use the host port from inside n8n.
