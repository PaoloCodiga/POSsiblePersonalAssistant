import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style"):
            self._ignored_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style") and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag.lower() in ("p", "br", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._ignored_depth:
            self.parts.append(data)


class EmailNormalizer:
    """Normalize provider-neutral email deliveries without provider credentials."""

    @staticmethod
    def _value(payload, key, default=None):
        body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        return payload.get(key, body.get(key, default))

    @classmethod
    def canonical_message_id(cls, value):
        if not value:
            return False
        value = re.sub(r"\s+", "", str(value))
        if not value:
            return False
        return value if value.startswith("<") and value.endswith(">") else "<%s>" % value.strip("<>")

    @staticmethod
    def normalize_timestamp(value):
        if not value:
            return False
        raw = str(value).strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
            return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        except ValueError:
            return re.sub(r"\s+", " ", raw).casefold()

    @staticmethod
    def normalize_addresses(value):
        if not value:
            return []
        if isinstance(value, str):
            value = [part.strip() for part in value.split(",") if part.strip()]
        result = []
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict):
                address = item.get("address") or item.get("email") or ""
                name = item.get("name") or ""
                normalized = {"name": str(name).strip(), "address": str(address).strip().casefold()}
            else:
                normalized = {"name": "", "address": str(item).strip().casefold()}
            if normalized["address"]:
                result.append(normalized)
        return result

    @classmethod
    def html_to_text(cls, value):
        if not value:
            return ""
        parser = _TextExtractor()
        parser.feed(str(value))
        return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()

    @staticmethod
    def normalize_subject(value):
        subject = re.sub(r"\s+", " ", str(value or "").strip())
        # RFC reply prefixes are only for conservative fallback comparison.
        while re.match(r"^(?:re|fw|fwd)\s*:\s*", subject, flags=re.IGNORECASE):
            subject = re.sub(r"^(?:re|fw|fwd)\s*:\s*", "", subject, flags=re.IGNORECASE).strip()
        return subject.casefold()

    @classmethod
    def fallback_identity(cls, values):
        canonical = "\x1f".join((
            str(values.get("mailbox_id") or "unconfigured"),
            ",".join(item["address"] for item in values["from"]),
            values["sent_at"] or values["received_at"] or "",
            cls.normalize_subject(values["subject"]),
            hashlib.sha256((values["text_body"] or "").encode("utf-8")).hexdigest(),
        ))
        return "email-fallback-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def normalize(cls, payload):
        html_body = cls._value(payload, "html_body", "") or ""
        text_body = cls._value(payload, "text_body", "") or cls.html_to_text(html_body)
        references = cls._value(payload, "references", []) or []
        if isinstance(references, str):
            references = re.findall(r"<[^>]+>|[^\s,]+", references)
        values = {
            "source": "email",
            "mailbox_id": cls._value(payload, "mailbox_id"),
            "external_event_id": cls._value(payload, "external_event_id") or cls._value(payload, "event_id"),
            "event_type": cls._value(payload, "event_type", "email_received"),
            "message_id": cls.canonical_message_id(cls._value(payload, "message_id")),
            "in_reply_to": cls.canonical_message_id(cls._value(payload, "in_reply_to")),
            "references": [item for item in (cls.canonical_message_id(item) for item in references) if item],
            "subject": str(cls._value(payload, "subject", "") or "").strip(),
            "from": cls.normalize_addresses(cls._value(payload, "from", [])),
            "to": cls.normalize_addresses(cls._value(payload, "to", [])),
            "cc": cls.normalize_addresses(cls._value(payload, "cc", [])),
            "bcc": cls.normalize_addresses(cls._value(payload, "bcc", [])),
            "received_at": cls.normalize_timestamp(cls._value(payload, "received_at") or cls._value(payload, "occurred_at")),
            "sent_at": cls.normalize_timestamp(cls._value(payload, "sent_at")),
            "folder": str(cls._value(payload, "folder", "INBOX") or "INBOX"),
            "imap_uid": str(cls._value(payload, "imap_uid")) if cls._value(payload, "imap_uid") is not None else False,
            "text_body": str(text_body or "").strip(),
            "html_body": str(html_body or ""),
            "has_attachments": bool(cls._value(payload, "has_attachments", False)),
            "attachments": cls._value(payload, "attachments", []) or [],
            "provider_thread_id": cls._value(payload, "provider_thread_id"),
            "external_reference": cls._value(payload, "external_reference"),
            "raw_payload": payload.get("raw_payload", payload),
        }
        mailbox_context = str(values["mailbox_id"] or "unconfigured")
        values["external_id"] = "email:%s:%s" % (
            mailbox_context, values["message_id"] or cls.fallback_identity(values),
        )
        return values
