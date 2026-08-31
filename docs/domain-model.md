# Domain model

`ppa.source` identifies adapters. `ppa.conversation` groups normalized `ppa.message` records. `ppa.meeting` represents source-neutral meetings. `ppa.flow` is an operational process/thread (for example a certification case or support incident) which can group Conversations and optionally belongs to an Odoo Project. A Project is the stable work container; a Flow is the more specific operational process; a Conversation is a communication thread; a Message is one communication.

Flows and Conversations use `open`, `in_progress`, `waiting`, `resolved`, and `ignored` operational states. Assigning a Flow with a Project makes its Conversation and newly ingested Messages inherit that Project. Removing a Flow or Project never deletes Messages or Conversations.

`ppa.mailbox` is a manager-only configuration record for an inbound protocol endpoint. It owns encrypted credential ciphertext, mailbox polling state, safe defaults, and Message/Ingestion Event traceability. Mailbox context is part of email identity, so identical RFC Message-IDs in different mailboxes remain distinct.

For email triage, `ppa.conversation.operational_state` is authoritative; `ppa.message.operational_state` is a related inbox convenience field. New incoming mail reopens resolved or ignored Conversations rather than being silently discarded.

`ppa.ai.analysis` persists audit history. Meeting analysis creates traceable `ppa.decision` and `ppa.suggested.action` records through `ai_analysis_id`, plus `ppa.open.question` records linked to both Meeting and Analysis.
# Ingestion events

`ppa.ingestion.event` is the audit record for an external delivery. It links a source and external event identifier to the normalized `ppa.meeting`. The resulting traceability is External Event → Ingestion Event → Meeting → AI Analysis → Decisions, Suggested Actions, and Open Questions.
## Global Work Queue

`ppa.suggested.action` is the PPA work item. It can reference a Message or Meeting and stores its source category, Flow, Project, Company, owner, priority, deadline, lifecycle state, and AI analysis traceability. A Flow aggregates conversations and work items; a Meeting may also be assigned to a Flow. `project.task` remains a distinct downstream Odoo record created only by explicit human confirmation.
