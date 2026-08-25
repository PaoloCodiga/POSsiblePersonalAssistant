# Architecture

Odoo 19 is PPA's business backoffice and system of record. PostgreSQL is accessed only through Odoo ORM. External systems are adapters and never write Odoo tables directly. Provider-neutral normalized messages and meetings retain raw payloads and source identity. AI-derived work first becomes `ppa.suggested.action`; only confirmation creates a native project task or mail activity. Decisions and actions retain source Many2one traceability. Native Odoo UI is preferred over custom frontend code.
