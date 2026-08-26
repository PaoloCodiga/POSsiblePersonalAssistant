# Plaud Ingestion

PPA does not call Plaud. Plaud AutoFlow and Zapier are external adapters; Zapier sends an event to the n8n development webhook at `POST /webhook/ppa/plaud`. n8n verifies its `PPA_N8N_WEBHOOK_SECRET`, normalizes the payload, then calls PPA over Docker networking at `http://ppa-odoo:8069/ppa/api/integrations/plaud`.

## Normalized contract

The Plaud endpoint accepts conventional HTTP JSON with `X-PPA-API-Key`. Required fields are `event_id`, `recording_id`, and an event type of `transcript_generated`, `summary_generated`, or `manual_import`. The recording ID is the stable Meeting identity and the event ID is the delivery identity. Raw payload is scrubbed of headers and common credential-bearing keys before persistence.

`ppa.ingestion.event` stores the delivery audit record. Its unique key is source plus external event ID. The canonical normalized Meeting uses source plus recording ID, so transcript-ready and summary-ready events merge into one Meeting. Empty values never erase an existing name, timestamp, summary, or transcript.

## Analysis safety

Phase 1.3A never starts Meeting Intelligence automatically. Plaud summary and transcript remain provider-supplied Meeting content, not `ppa.ai.analysis`. Replayed event deliveries return the existing ingestion event and do not create another AI Analysis. Human users may analyze a Meeting later through the existing Odoo action.

## Retry and backfill

Managers can retry failed ingestion events from the native Odoo form. The same stored payload is processed and `retry_count` is incremented; no new audit event is created. Historical Plaud backfill is deliberately not implemented in Phase 1.3. A future CLI must emit this same normalized contract through the PPA HTTP API rather than writing PostgreSQL directly.
