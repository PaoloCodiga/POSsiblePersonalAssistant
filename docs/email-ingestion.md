# Email ingestion foundation

Phase 2.1A defines a provider-neutral incoming-email foundation. Phase 2.1A.1 adds secure multi-mailbox configuration, but does not fetch from a mailbox, send or draft email, ingest attachment binaries, or backfill history.

```
Email → Ingestion Event → Message → Conversation → Flow → Project
Message → Message Intelligence → Importance / Category / Needs Reply → Suggested Actions → To Confirm
```

`POST /ppa/api/ingestion/events` accepts `source=email`, `external_event_id`, `event_type=email_received`, and a `payload` containing `message_id`, reply headers, address lists, timestamps, folder, bodies, and attachment metadata. n8n will later map provider-specific IMAP data into this contract.

## Multiple mailboxes and secrets

```
Multiple mailboxes → ppa.mailbox → secure protocol adapter → MailboxSyncService → existing email ingestion architecture
```

`ppa.mailbox` is manager-only and holds connection metadata, default Flow/Project/owner context, and synchronization diagnostics. Its password replacement field is write-only: `PPA_SECRET_ENCRYPTION_KEY` is a Fernet key supplied by the runtime; only the authenticated encrypted ciphertext is stored in PostgreSQL. The key is never stored in PostgreSQL or committed. Generate it once in production with a cryptographically secure Fernet-key generator, keep it in secret management permanently, and do not rotate it without a controlled credential re-encryption procedure.

The Test Connection action validates DNS/TCP/TLS, authentication, and the configured folder only. It does not fetch or persist messages and does not change the UID cursor. There is never one cron per mailbox: one central scheduled job independently selects active due mailboxes by poll interval.

## Swizzonic IMAP activation

The real IMAP adapter reads only the mailbox fields; it does not hardcode a provider. For the future first mailbox, create a record manually as **Paolo Possible** with `paolo.codiga@possible.ch`, protocol `IMAP`, host `mail-ch.securemail.pro`, port `993`, SSL enabled, STARTTLS disabled, folder `INBOX`, poll interval five minutes, and **Active disabled**. Enter the password only into the masked replacement field.

First use must be **Test Connection**, then **Initialize From Current Inbox**. Initialization reads UIDVALIDITY and records the highest current IMAP UID while importing **zero** historical messages. Only after that may a manager enable the mailbox and use **Sync Now** or the central cron. Sync reads UIDs greater than `last_uid` in order; every completed email advances the cursor. A malformed or failed message stops the mailbox at the last successful UID. A UIDVALIDITY mismatch sets **Needs Attention**, imports nothing, and requires manager re-initialization rather than silently re-importing the inbox.

The adapter parses RFC headers, text/plain and text/html MIME alternatives, and attachment metadata only. It never stores attachment binaries. Plain text is preferred for intelligence; HTML-only email is reduced to inert text by the existing normalizer. `PPA_AUTO_ANALYZE_MESSAGES=false` is the default, so initial production debugging is ingestion-only. Enabling it later remains advisory: no task, activity, outgoing email, draft, or reply is created.

## Operator triage

When `PPA_AUTO_ANALYZE_MESSAGES=true`, a successfully persisted incoming Message is analyzed after ingestion. Analysis failure creates an auditable failed analysis without failing the email event or mailbox cursor. The **Inbox → Emails** view defaults to open incoming emails, prioritised critical → important → normal → low. It provides Flow, Project, mailbox, owner, sender, reply-needed, and operational-state filters.

Conversation is the operational-state source of truth. Operators use Start Work, Waiting, Resolve, Ignore, and Reopen; those actions have no external side effects. A new incoming email in a resolved or ignored Conversation reopens it to `open`. AI produces only summary, controlled category/importance, needs reply, confidence, suggestion text, and Suggested Actions. It resolves Flow/Project only by safe exact matches, resolves owner only to a unique active user, and never overwrites existing context or creates work automatically.

Troubleshooting: use Test Connection for TLS/authentication/folder errors; inspect the manager-only sanitized mailbox diagnostic and related Ingestion Event. Never paste a password into a diagnostic, log, or source file. A UIDVALIDITY change is resolved only by reviewing the mailbox and initializing from its current position again.

Message identity is mailbox plus RFC Message-ID. When Message-ID is missing, PPA hashes mailbox context, normalized sender, sent/received timestamp, subject, and plain-text body hash; it never uses a random identifier or processing time. Delivery event identity remains separate, so later richer delivery metadata can be audited while enriching the same Message non-destructively.

Conversation resolution prefers `In-Reply-To`, then `References`, then a future provider thread ID. Subject matching is only used when an exact normalized subject and sender identify exactly one existing conversation; similar subjects do not merge automatically. Reply prefixes such as `Re:`, `Fw:`, and `Fwd:` are removed only for this fallback comparison.

Flow resolution reuses a Conversation Flow, a uniquely referenced Flow, or a unique exact external reference; it never performs fuzzy matching or creates a Flow. A Flow Project is inherited by its Conversation and new Messages. New incoming emails start `open`; AI cannot resolve or ignore them automatically.

Attachment support is metadata only (`filename`, `mime_type`, `size`, `content_id`). Binary attachment ingestion is deferred to Phase 2.1B/2.2.

## Future Swizzonic adapter

The future n8n flow will be `Swizzonic IMAP → n8n → normalized email_received → PPA`. It will monitor only new incoming messages from `INBOX`; historical import is a separate controlled operation. The intended first mailbox is `paolo.codiga@possible.ch`, with IMAP host `mail-ch.securemail.pro`, port `993`, SSL enabled, and folder `INBOX`. No record or credential is created in this phase. Credentials must be stored only in approved production secret management/n8n credentials, never in the repository, logs, or PPA source.
