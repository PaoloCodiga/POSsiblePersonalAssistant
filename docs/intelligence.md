# Intelligence Core

`ppa.message` is analyzed by `IntelligenceService`, which selects a provider: deterministic `FakeProvider` for tests/local development or `OpenAiProvider` for configured development. Each execution persists `ppa.ai.analysis` with prompt version `message-analysis-v1`.

```
Message → AI Analysis → Suggested Action → human confirmation → Task or Activity
```

AI analysis never creates `project.task` or `mail.activity` directly. Suggested actions remain `to_confirm`. Re-analysis preserves historical analyses and suggestions; the latest successful result updates message convenience fields.

Set `PPA_AI_PROVIDER=fake` for deterministic operation. For OpenAI set `PPA_AI_PROVIDER=openai`, `PPA_OPENAI_API_KEY`, optional `PPA_OPENAI_MODEL`, and `PPA_AI_TIMEOUT_SECONDS`. Missing OpenAI configuration fails only when an analysis is requested.
