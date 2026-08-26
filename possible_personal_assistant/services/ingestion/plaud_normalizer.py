class PlaudNormalizer:
    """Normalize adapter payloads into PPA's provider-neutral meeting contract."""

    @classmethod
    def normalize(cls, payload):
        return {
            "source": payload.get("source"),
            "external_id": payload.get("external_id"),
            "external_event_id": payload.get("external_event_id"),
            "event_type": payload.get("event_type", "unknown"),
            "name": payload.get("name"),
            "started_at": payload.get("started_at"),
            "ended_at": payload.get("ended_at"),
            "summary": payload.get("summary"),
            "transcript": payload.get("transcript"),
            "participants": payload.get("participants") or [],
            "source_url": payload.get("source_url"),
        }
