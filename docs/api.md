# PPA HTTP API

Protocol: conventional HTTP. Payload: JSON. Authentication: `X-PPA-API-Key`. No JSON-RPC envelope is required. The development base URL is `http://localhost:${PPA_ODOO_PORT}` (default `42001`).

`GET /ppa/api/health` returns 200 with a valid key and 401 otherwise. `POST /ppa/api/messages`, `/ppa/api/meetings`, and `/ppa/api/suggested-actions` accept JSON objects.

Messages and meetings are retry-safe: `source + external_id` is unique. A new record returns `201` / `status: created`; a duplicate returns `200` / `status: existing` with the original ID.

Suggested actions always start in `to_confirm`. Ingestion never creates a project task or mail activity. Human confirmation creates a `project.task` when a project is selected, otherwise a `mail.activity`.

```powershell
$baseUrl = "http://localhost:42001"
$headers = @{ "X-PPA-API-Key" = "<your-api-key>" }
Invoke-RestMethod "$baseUrl/ppa/api/health" -Headers $headers

$message = @{ source = "email"; external_id = "example-message-001"; conversation_external_id = "example-thread-001"; sender_name = "John Smith"; sender_address = "john@example.com"; subject = "Quotation"; body = "Can you send the quotation by Friday?"; received_at = "2026-08-25T10:00:00Z"; raw_payload = @{ example = $true } } | ConvertTo-Json -Depth 10
Invoke-RestMethod "$baseUrl/ppa/api/messages" -Method Post -Headers $headers -ContentType "application/json" -Body $message

$meeting = @{ source = "plaud"; external_id = "example-meeting-001"; name = "Weekly meeting" } | ConvertTo-Json
Invoke-RestMethod "$baseUrl/ppa/api/meetings" -Method Post -Headers $headers -ContentType "application/json" -Body $meeting

$action = @{ name = "Verify prices"; source_type = "manual"; priority = "important" } | ConvertTo-Json
Invoke-RestMethod "$baseUrl/ppa/api/suggested-actions" -Method Post -Headers $headers -ContentType "application/json" -Body $action
```

```bash
curl -H 'X-PPA-API-Key: <your-api-key>' http://localhost:42001/ppa/api/health
curl -X POST http://localhost:42001/ppa/api/messages -H 'X-PPA-API-Key: <your-api-key>' -H 'Content-Type: application/json' -d '{"source":"email","external_id":"example-message-001"}'
```
# Ingestion event endpoint

`POST /ppa/api/ingestion/events` is conventional HTTP JSON, protected by `X-PPA-API-Key`. It creates an audit event and creates or merges a normalized Meeting. A new event returns `201`; a replay of the same source and external event ID returns `200` with `status: existing`. Invalid events return `400` and retain a failed audit record when their source and event ID are available.

`POST /ppa/api/integrations/plaud` accepts Plaud-normalized fields `event_id`, `event_type`, and either a recording/file ID or `create_time`. A recording/file ID is the Meeting external ID when supplied; otherwise PPA derives it solely from normalized Create Time. Event IDs remain idempotency keys.
