# Plaud Ingestion

PPA has no private Plaud API integration and does not scrape Plaud. The supported connection is Plaud → Zapier → n8n → `POST /ppa/api/ingestion/events` → `ppa.ingestion.event` → `ppa.meeting`. n8n is the provider-specific mapping boundary and Odoo remains the system of record.

## Implemented contract

n8n accepts `POST /webhook/ppa/plaud` only when `X-PPA-Plaud-Key` matches `PPA_PLAUD_WEBHOOK_KEY`. Missing or invalid keys receive `401` with `{"error":"unauthorized"}` and stop before normalization or forwarding. Valid requests receive success only after the PPA request completes. n8n forwards the provider-neutral PPA payload to `PPA_ODOO_INTERNAL_URL` with the separate internal `PPA_API_KEY`.

The forwarded contract uses the established PPA fields: `source=plaud`, `external_event_id`, `external_id`, `event_type`, and meeting fields. `external_id` is the Plaud recording/file identifier and is the stable Meeting identity. `external_event_id` is the delivery identity, unique per source. Transcript and summary events therefore merge into the same Meeting in either order; empty partial values never erase useful stored content.

The n8n mapping accepts common Zapier spellings such as `recording_id`, `recordingId`, `file_id`, `event_id`, `eventId`, `transcript`, and `summary`. A supplied Plaud recording/file ID remains the Meeting identity. The real **Transcript & Summary Ready** trigger may not expose one, so n8n deterministically derives `plaud-derived-<hash>` from normalized title and create time. A supplied Zapier/Plaud event ID is preferred; otherwise n8n derives the event ID from the resolved Meeting identity, event type, and content. It never uses a random UUID, so retries remain idempotent. Inspect the n8n execution's **Input** and **Output** panels for a test event's field *names*; update only this mapping after observing an actual Zapier sample. Avoid retaining full transcripts in debug logs.

Raw audit payloads are recursively scrubbed of headers and credential-bearing keys before Odoo persists them. Managers can inspect the sanitized payload in the native Ingestion Events form. Failed events may be retried in place; retry increments `retry_count` and reuses the audit record.

## Real Plaud → Zapier → n8n Setup

1. In Plaud Web, open **Explore → Integrations**, find **Zapier**, and select **Go to Zapier**.
2. In Zapier, connect the Plaud account and allow the requested access.
3. Create a Zap with Plaud's available **Transcript & Summary Ready** trigger. It maps to PPA's normalized `meeting_ready` event.
4. Add **Webhooks by Zapier** as a `POST` action to the n8n development URL: `https://<reachable-host>/webhook/ppa/plaud`.
5. Add header `X-PPA-Plaud-Key` with the configured `PPA_PLAUD_WEBHOOK_KEY` value.
6. Map the supplied recording/file identifier, trigger type, event identifier or generation/update timestamp, title, transcript or summary, timestamps, participants, and source URL. Do not map Plaud credentials or request headers into the body.
7. Run Zapier's test step. In n8n, inspect the normalized output and only then publish the Zap.

Plaud officially supports Zapier as a trigger for transcript-generated and summary-generated events; Plaud is not a Zapier action. See [Plaud's Zapier integration guide](https://support.plaud.ai/hc/en-us/articles/12200669941647-Zapier-integration).

## Analysis safety

`PPA_AUTO_ANALYZE_MEETINGS=false` is the default. Ingestion alone never creates tasks or activities. For a controlled second test, set `PPA_AUTO_ANALYZE_MEETINGS=true` and restart Odoo: only a completed `meeting_ready` event with a transcript is eligible. A completed Meeting analysis prevents replayed delivery from creating another automatic analysis. Suggested Actions remain `to_confirm`; no project task or mail activity is automatically created.

## Scope and recovery

Real Plaud/Zapier production delivery is configured manually and was not claimed as tested until an account owner runs a Zap. Historical CLI backfill is future recovery work for missing recordings or repair and must submit the same PPA HTTP contract. Plaud MCP is a future interactive/query option, not an ingestion mechanism.
