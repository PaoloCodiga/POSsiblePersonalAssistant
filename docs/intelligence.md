# Intelligence Core

`ppa.message` is analyzed by `IntelligenceService`, which selects a provider: deterministic `FakeProvider` for tests/local development or `OpenAiProvider` for configured development. Each execution persists `ppa.ai.analysis` with prompt version `message-analysis-v2`.

```
Message → AI Analysis → Suggested Action → human confirmation → Task or Activity
```

AI analysis never creates `project.task` or `mail.activity` directly. Suggested actions remain `to_confirm`. Re-analysis preserves historical analyses and suggestions; the latest successful result updates message convenience fields.

For incoming email, Message Intelligence records summary, controlled category, importance, needs reply, confidence, suggested Flow/Project/owner text, and Suggested Actions. Suggestions are advisory only: they never assign or create a Flow/Project, change the Conversation operational state, create work, draft a reply, or send email. Plain email text is preferred; HTML-only bodies are reduced to inert text before analysis.

With `PPA_AUTO_ANALYZE_MESSAGES=true`, analysis runs only after a new incoming email has been persisted. Replay detection prevents repeated automatic analysis for the same successfully analyzed Message; manual re-analysis remains available and creates historical records. Failed analysis is audited and leaves the Message and Conversation operationally available.

Set `PPA_AI_PROVIDER=fake` for deterministic operation. For OpenAI set `PPA_AI_PROVIDER=openai`, `PPA_OPENAI_API_KEY`, optional `PPA_OPENAI_MODEL`, and `PPA_AI_TIMEOUT_SECONDS`. Missing OpenAI configuration fails only when an analysis is requested.

## Meeting Intelligence

`meeting-analysis-v1` uses `Meeting → IntelligenceService → AiProvider → AI Analysis`. A completed analysis creates traceable Decisions, Suggested Actions, and Open Questions. AI analysis never creates `project.task` or `mail.activity` directly; Suggested Actions stay `to_confirm` until human confirmation.

Meeting output is validated before downstream records are created. Invalid enums, confidence outside 0.0–1.0, or malformed entries produce a failed analysis without partial output. Owner matching uses only active users, case-insensitive whitespace-normalized exact names, and requires one unique match. Raw owner text remains available for review.

Meetings retain multiple historical analyses. A later successful analysis updates convenience fields but preserves prior intelligence records. A failed re-analysis never replaces the last successful state.
## Work-item output

Meeting and Message Intelligence may suggest actions. Each suggested action is stored as a `ppa.suggested.action` in `to_confirm`, with source, confidence, priority, and optional deadline traceability. Re-analysis creates additional historical suggestions; it does not overwrite manual work context or reset completed/rejected work. No suggested action is automatically confirmed, sent, scheduled, or converted to a task/activity.
