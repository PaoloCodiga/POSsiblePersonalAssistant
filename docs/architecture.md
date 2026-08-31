# Architecture

Odoo 19 is PPA's business backoffice and system of record. PostgreSQL is accessed only through Odoo ORM. External systems are adapters and never write Odoo tables directly. Provider-neutral normalized messages and meetings retain raw payloads and source identity. AI-derived work first becomes `ppa.suggested.action`; only confirmation creates a native project task or mail activity. Decisions and actions retain source Many2one traceability. Native Odoo UI is preferred over custom frontend code.
# Plaud ingestion boundary

Plaud, Zapier, and n8n are adapters, not PPA domain dependencies. Zapier bridges Plaud's official transcript/summary triggers to n8n. n8n authenticates the public webhook, maps provider-specific fields, and submits the provider-neutral normalized contract to PPA. PPA creates an auditable `ppa.ingestion.event`, then creates or merges the normalized `ppa.meeting`; optional configuration-controlled AI analysis occurs only after that Meeting exists.

# Email ingestion boundary

Future mail adapters submit a provider-neutral `email_received` event to `/ppa/api/ingestion/events`; neither IMAP nor credentials live in PPA's domain services. The trace is `Email → Ingestion Event → Message → Conversation → Flow → Project`. Normalization, email conversation resolution, and Flow resolution are isolated services so a future Swizzonic IMAP/n8n adapter, Microsoft Graph, or Gmail API can use the same core contract. Flow matching is deterministic only and never creates a Flow.

`ppa.mailbox → MailboxSyncService → IMAP protocol adapter → IngestionService` is the manager-controlled, multi-mailbox boundary. Passwords are Fernet-encrypted in the application using the runtime-only `PPA_SECRET_ENCRYPTION_KEY`; ordinary ORM reads and UI never reveal plaintext. One central cron selects due active mailboxes. Bootstrap records UIDVALIDITY and the current highest UID without importing history; normal sync fetches only newer UIDs, and a UIDVALIDITY reset stops automatic synchronization for manager action.
## Global Work Queue

Email and meeting intelligence create `ppa.suggested.action` records as `to_confirm`. The native Global Work Queue reads that one model across sources. Source context is derived once from Message or Meeting records and remains auditable through the source and AI analysis references. Confirmation is the only boundary that may create a native Odoo task or activity; queue state transitions have no other external side effects.
