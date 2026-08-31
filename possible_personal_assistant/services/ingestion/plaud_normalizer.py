import re
from datetime import datetime, timezone


class PlaudNormalizer:
    """Normalize adapter payloads into PPA's provider-neutral meeting contract."""

    @classmethod
    def normalize_create_time(cls, value):
        """Return a stable UTC representation of Plaud's immutable create time."""
        if value is None:
            return False
        raw_value = re.sub(r"\s+", " ", str(value).strip())
        if not raw_value:
            return False
        try:
            if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", raw_value):
                timestamp = float(raw_value)
                # Plaud/Zapier timestamps may be sent as Unix seconds or milliseconds.
                if abs(timestamp) >= 100000000000:
                    timestamp /= 1000
                parsed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            else:
                parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                else:
                    parsed = parsed.astimezone(timezone.utc)
            # Match JavaScript's Date#toISOString representation used by n8n.
            return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        except (OverflowError, ValueError):
            # Preserve an unparseable provider value deterministically rather than
            # silently accepting whitespace/case variants as separate identities.
            return raw_value.casefold()

    @classmethod
    def external_meeting_id(cls, payload):
        """Prefer a real Plaud ID; otherwise derive identity solely from create time."""
        recording_id = next((payload.get(key) for key in (
            "recording_id", "recordingId", "file_id", "fileId",
        ) if payload.get(key)), False)
        if recording_id:
            return str(recording_id)
        create_time = cls.normalize_create_time(payload.get("create_time") or payload.get("createTime"))
        if create_time:
            # FNV-1a 32-bit matches the deterministic n8n workflow implementation.
            digest = 2166136261
            for character in create_time:
                digest ^= ord(character)
                digest = (digest * 16777619) & 0xFFFFFFFF
            return "plaud-created-{:x}".format(digest)
        # Preserve provider-neutral Plaud payloads that were normalized before
        # Create Time became mandatory for the fallback strategy.
        return payload.get("external_id") or False

    @classmethod
    def normalize(cls, payload):
        create_time = cls.normalize_create_time(payload.get("create_time") or payload.get("createTime"))
        return {
            "source": payload.get("source"),
            "external_id": cls.external_meeting_id(payload),
            # Keep a supplied immutable Plaud identifier through the second
            # normalization that occurs while processing the audit event.
            "recording_id": payload.get("recording_id") or payload.get("recordingId"),
            "file_id": payload.get("file_id") or payload.get("fileId"),
            "external_event_id": payload.get("external_event_id"),
            "event_type": payload.get("event_type", "unknown"),
            "create_time": create_time,
            "name": payload.get("name"),
            "started_at": payload.get("started_at"),
            "ended_at": payload.get("ended_at"),
            "summary": payload.get("summary"),
            "transcript": payload.get("transcript"),
            "participants": payload.get("participants") or [],
            "source_url": payload.get("source_url"),
        }
