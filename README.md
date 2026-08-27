# POSsible Personal Assistant

PPA is an Odoo 19 Community operational-backoffice foundation. Odoo is the system of record; external providers will use the authenticated PPA API and never write PostgreSQL directly.

Copy `.env.example` to `.env`, choose secrets, then run `./scripts/start.ps1`. Open `http://localhost:${PPA_ODOO_PORT}` (default `42001`), create/select database `ppa`, and install **POSsible Personal Assistant**. Use `./scripts/update-module.ps1` to upgrade and `./scripts/test-module.ps1` for Odoo tests. `./scripts/stop.ps1`, `./scripts/reset.ps1`, and `./scripts/logs.ps1` manage the stack.

The ingestion API is conventional HTTP with JSON payloads and `X-PPA-API-Key` authentication; it does not use JSON-RPC. See [API documentation](docs/api.md). PostgreSQL at `localhost:${PPA_POSTGRES_PORT}` is development-only and must not be publicly exposed in production.
# Plaud ingestion development support

Phase 1.4 provides a Plaud → Zapier → n8n → PPA ingestion mapping workflow. See [Plaud ingestion](docs/plaud-ingestion.md). No Plaud private API, scraping, or Plaud credential storage is implemented.
