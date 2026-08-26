# Architecture

Odoo 19 is PPA's business backoffice and system of record. PostgreSQL is accessed only through Odoo ORM. External systems are adapters and never write Odoo tables directly. Provider-neutral normalized messages and meetings retain raw payloads and source identity. AI-derived work first becomes `ppa.suggested.action`; only confirmation creates a native project task or mail activity. Decisions and actions retain source Many2one traceability. Native Odoo UI is preferred over custom frontend code.
# Plaud ingestion boundary

Plaud, Zapier, and n8n are adapters, not PPA domain dependencies. n8n submits the provider-neutral normalized event contract to PPA. PPA creates an auditable `ppa.ingestion.event`, then creates or merges the normalized `ppa.meeting`; optional AI analysis occurs only after that Meeting exists.
