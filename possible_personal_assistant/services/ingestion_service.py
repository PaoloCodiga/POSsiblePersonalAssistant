import json
import logging
import os
import re

from odoo import fields

from .ingestion.plaud_normalizer import PlaudNormalizer

_logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, env):
        self.env = env

    def ingest_event(self, payload):
        source = self.env["ppa.source"].search([("code", "=", payload.get("source"))], limit=1)
        if not source:
            source = self.env.ref("possible_personal_assistant.source_unknown")
        event_id = payload.get("external_event_id")
        if event_id:
            existing = self.env["ppa.ingestion.event"].search([
                ("source_id", "=", source.id), ("external_event_id", "=", event_id),
            ], limit=1)
            if existing:
                return existing, False
        event = self.env["ppa.ingestion.event"].create({
            "name": "Ingestion: %s" % (event_id or payload.get("external_id") or "unknown"),
            "source_id": source.id,
            "external_event_id": event_id,
            "external_object_id": payload.get("external_id"),
            "event_type": payload.get("event_type", "unknown"),
            "raw_payload_json": json.dumps(self._safe_payload(payload.get("raw_payload", payload))),
        })
        self._process_event(event, payload)
        return event, True

    def retry_event(self, event):
        payload = json.loads(event.normalized_payload_json or event.raw_payload_json or "{}")
        event.write({"retry_count": event.retry_count + 1, "error_message": False})
        self._process_event(event, payload)
        return event

    def _process_event(self, event, payload):
        event.write({"status": "processing"})
        try:
            normalized = PlaudNormalizer.normalize(payload)
            self._validate(normalized, event.source_id)
            event.write({"normalized_payload_json": json.dumps(normalized)})
            meeting = self._upsert_meeting(event, normalized)
            event.write({"status": "completed", "meeting_id": meeting.id,
                         "processed_at": fields.Datetime.now(), "error_message": False})
            self._auto_analyze_meeting(event, meeting)
        except Exception as error:
            _logger.warning("PPA ingestion event %s failed: %s", event.id, error)
            event.write({"status": "failed", "error_message": str(error)[:500],
                         "processed_at": fields.Datetime.now()})
        return event

    def _auto_analyze_meeting(self, event, meeting):
        if os.getenv("PPA_AUTO_ANALYZE_MEETINGS", "false").lower() != "true":
            return
        if event.event_type != "meeting_ready" or not meeting.transcript:
            return
        if self.env["ppa.ai.analysis"].search_count([
            ("meeting_id", "=", meeting.id), ("status", "=", "completed"),
        ]):
            _logger.info("PPA ingestion event %s skipped duplicate meeting analysis for meeting %s", event.id, meeting.id)
            return
        try:
            from .intelligence_service import IntelligenceService
            analysis = IntelligenceService(self.env).analyze_meeting(meeting)
            _logger.info(
                "PPA ingestion event %s auto-analysis %s for meeting %s",
                event.id, analysis.status, meeting.id,
            )
        except Exception as error:
            _logger.warning("PPA ingestion event %s auto-analysis failed for meeting %s: %s", event.id, meeting.id, error)

    def _validate(self, payload, source):
        if source.code == "unknown" or not payload.get("source"):
            raise ValueError("Unknown PPA source.")
        if not payload.get("external_id"):
            raise ValueError("external_id is required.")
        if payload["event_type"] not in dict(self.env["ppa.ingestion.event"]._fields["event_type"].selection):
            raise ValueError("Invalid event type.")

    def _upsert_meeting(self, event, payload):
        Meeting = self.env["ppa.meeting"]
        meeting = Meeting.search([("source_id", "=", event.source_id.id),
                                  ("external_id", "=", payload["external_id"])], limit=1)
        values = {"source_id": event.source_id.id, "external_id": payload["external_id"]}
        values["last_ingested_at"] = fields.Datetime.now()
        for key in ("name", "summary", "transcript"):
            if payload.get(key):
                values[key] = payload[key]
        for key in ("started_at", "ended_at"):
            if payload.get(key):
                values[key] = fields.Datetime.to_datetime(payload[key])
        if payload.get("source_url"):
            values["external_url"] = payload["source_url"]
        participant_ids, participant_names = self._participants(payload.get("participants", []))
        if participant_names:
            existing_names = self._participant_names(meeting) if meeting else []
            values["participant_names_json"] = json.dumps(list(dict.fromkeys(existing_names + participant_names)))
        if meeting:
            if participant_ids:
                values["participant_ids"] = [(4, partner_id) for partner_id in participant_ids]
            meeting.write(values)
        else:
            values["name"] = values.get("name") or payload["external_id"]
            values["participant_ids"] = [(6, 0, participant_ids)]
            meeting = Meeting.create(values)
        return meeting

    @staticmethod
    def _participant_names(meeting):
        try:
            names = json.loads(meeting.participant_names_json or "[]")
        except (TypeError, ValueError):
            return []
        return [name for name in names if isinstance(name, str) and name]

    def _participants(self, participants):
        names, partner_ids = [], []
        for participant in participants:
            name = participant.get("name") if isinstance(participant, dict) else str(participant)
            if not name:
                continue
            names.append(name)
            normalized = self._normalize(name)
            matches = self.env["res.partner"].search([]).filtered(
                lambda partner: self._normalize(partner.name) == normalized)
            if len(matches) == 1:
                partner_ids.append(matches.id)
        return partner_ids, names

    @staticmethod
    def _normalize(value):
        return re.sub(r"\s+", " ", (value or "").strip()).casefold()

    @classmethod
    def _safe_payload(cls, value):
        if isinstance(value, list):
            return [cls._safe_payload(item) for item in value]
        if not isinstance(value, dict):
            return value
        sensitive = ("authorization", "api_key", "apikey", "secret", "token", "password", "cookie")
        return {
            key: cls._safe_payload(item)
            for key, item in value.items()
            if (
                key.lower() != "headers"
                and not any(
                    marker in key.lower().replace("-", "_")
                    for marker in sensitive
                )
            )
        }
