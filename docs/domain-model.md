# Domain model

`ppa.source` identifies adapters. `ppa.conversation` groups normalized `ppa.message` records. `ppa.meeting` represents source-neutral meetings. `ppa.decision` and `ppa.suggested.action` reference one message or meeting when externally derived. Suggested actions are review records; confirmation creates `project.task` when a project is selected, otherwise a `mail.activity`. Completing a task does not force a project stage, so each project's workflow remains authoritative.

`ppa.ai.analysis` persists audit history. Meeting analysis creates traceable `ppa.decision` and `ppa.suggested.action` records through `ai_analysis_id`, plus `ppa.open.question` records linked to both Meeting and Analysis.
# Ingestion events

`ppa.ingestion.event` is the audit record for an external delivery. It links a source and external event identifier to the normalized `ppa.meeting`. The resulting traceability is External Event → Ingestion Event → Meeting → AI Analysis → Decisions, Suggested Actions, and Open Questions.
