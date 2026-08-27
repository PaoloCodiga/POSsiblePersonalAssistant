# n8n

Future flow: Email / Teams / Telegram / WhatsApp / Plaud → n8n → future PPA Gateway / AI → PPA Odoo API. No production workflows are included in Phase 1.
# Plaud development workflow

Import `workflows/plaud-meeting-ingestion.json` into n8n. It receives Zapier at `POST /webhook/ppa/plaud`, requires `X-PPA-Plaud-Key` to match `PPA_PLAUD_WEBHOOK_KEY`, normalizes Zapier field variants, and calls PPA internally at `PPA_ODOO_INTERNAL_URL` with the separate `PPA_API_KEY`. Missing or invalid webhook keys receive JSON `401` before normalization or forwarding; valid requests receive a success response after PPA accepts the event. Do not use the host port from inside n8n.
