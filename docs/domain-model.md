# Domain model

`ppa.source` identifies adapters. `ppa.conversation` groups normalized `ppa.message` records. `ppa.meeting` represents source-neutral meetings. `ppa.decision` and `ppa.suggested.action` reference one message or meeting when externally derived. Suggested actions are review records; confirmation creates `project.task` when a project is selected, otherwise a `mail.activity`. Completing a task does not force a project stage, so each project's workflow remains authoritative.
