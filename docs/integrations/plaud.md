# Plaud Integration

The implemented Phase 1.3A route is Plaud → Zapier → n8n → `POST /ppa/api/integrations/plaud`. Zapier forwards only its supported Transcript Generated and Summary Generated trigger payloads; n8n performs normalization and holds the PPA API key. PPA stores no Plaud credential and does not call or scrape Plaud.

The recording ID is the stable Meeting identity and the delivery event ID is the event idempotency key. Transcript and summary events merge safely into one provider-neutral Meeting. Phase 1.3A never starts Meeting Intelligence automatically. Future CLI backfill must submit the same normalized contract through PPA rather than writing the database directly.
