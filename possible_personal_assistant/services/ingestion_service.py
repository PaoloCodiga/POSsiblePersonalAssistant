import json
import logging
import os
import re
from datetime import datetime

from odoo import fields

from .ingestion.plaud_normalizer import PlaudNormalizer
from .ingestion.email_normalizer import EmailNormalizer
from .email_conversation_resolver import EmailConversationResolver
from .flow_resolver import FlowResolver

_logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, env):
        self.env = env

    def ingest_event(self, payload):
        # Resolve Plaud's Meeting identity before the audit event is created, so
        # its external object ID records the same immutable key used for merging.
        if payload.get("source") == "plaud":
            raw_payload = payload.get("raw_payload", payload)
            payload = PlaudNormalizer.normalize(payload)
            payload["raw_payload"] = raw_payload
        elif payload.get("source") == "email":
            raw_payload = payload.get("raw_payload", payload)
            payload = EmailNormalizer.normalize(payload)
            payload["raw_payload"] = raw_payload
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
            "mailbox_id": payload.get("mailbox_id") if payload.get("source") == "email" else False,
            "external_event_id": event_id,
            "external_object_id": payload.get("external_id"),
            "imap_uid": payload.get("imap_uid") if payload.get("source") == "email" else False,
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
            normalized = EmailNormalizer.normalize(payload) if event.source_id.code == "email" else PlaudNormalizer.normalize(payload)
            self._validate(normalized, event.source_id)
            event.write({"normalized_payload_json": json.dumps(normalized)})
            if event.source_id.code == "email":
                message, conversation = self._upsert_email(event, normalized)
                event.write({"status": "completed", "message_id": message.id, "conversation_id": conversation.id,
                             "processed_at": fields.Datetime.now(), "error_message": False})
                self._auto_analyze_message(event, message)
            else:
                meeting = self._upsert_meeting(event, normalized)
                event.write({"status": "completed", "meeting_id": meeting.id,
                             "processed_at": fields.Datetime.now(), "error_message": False})
                self._auto_analyze_meeting(event, meeting)
        except Exception as error:
            _logger.warning("PPA ingestion event %s failed: %s", event.id, error)
            event.write({"status": "failed", "error_message": str(error)[:500],
                         "processed_at": fields.Datetime.now()})
        return event

    def _upsert_email(self, event, payload):
        Message = self.env["ppa.message"]
        message = Message.search([
            ("source_id", "=", event.source_id.id), ("external_id", "=", payload["external_id"]),
        ], limit=1)
        resolver = EmailConversationResolver(self.env, event.source_id)
        conversation = message.conversation_id if message and message.conversation_id else resolver.resolve(payload)
        if not conversation:
            external_id = "email-thread:%s" % payload["provider_thread_id"] if payload.get("provider_thread_id") else False
            conversation = self.env["ppa.conversation"].create({
                "name": payload.get("subject") or payload["external_id"], "source_id": event.source_id.id,
                "mailbox_id": payload.get("mailbox_id"), "external_id": external_id, "operational_state": "open",
            })
        flow = FlowResolver(self.env).resolve(
            conversation, payload.get("external_reference"), event.source_id,
            [payload.get("in_reply_to")] + payload.get("references", []),
        )
        if flow and not conversation.flow_id:
            conversation.write({"flow_id": flow.id})
        mailbox = self.env["ppa.mailbox"].browse(payload.get("mailbox_id"))
        if mailbox and not conversation.flow_id and not conversation.project_id:
            if mailbox.default_flow_id:
                conversation.write({"flow_id": mailbox.default_flow_id.id})
            elif mailbox.default_project_id:
                conversation.write({"project_id": mailbox.default_project_id.id})
        values = self._email_values(payload, conversation, mailbox)
        if message:
            # Enrichment is intentionally non-destructive: blanks never erase data.
            values = {key: value for key, value in values.items() if value not in (False, None, "", [], "[]")}
            if values:
                message.write(values)
        else:
            message = Message.create(values)
        timestamp = message.received_at or message.sent_at
        if timestamp and (not conversation.last_message_at or timestamp > conversation.last_message_at):
            conversation.last_message_at = timestamp
        if flow:
            flow_values = {}
            if timestamp and (not flow.first_activity_at or timestamp < flow.first_activity_at):
                flow_values["first_activity_at"] = timestamp
            if timestamp and (not flow.last_activity_at or timestamp > flow.last_activity_at):
                flow_values["last_activity_at"] = timestamp
            if flow_values:
                flow.write(flow_values)
        return message, conversation

    @staticmethod
    def _email_values(payload, conversation, mailbox):
        sender = payload.get("from", [])
        first_sender = sender[0] if sender else {}
        html_or_text = payload.get("html_body") or payload.get("text_body")
        return {
            "name": payload.get("subject") or payload["external_id"], "source_id": conversation.source_id.id,
            "mailbox_id": mailbox.id, "external_id": payload["external_id"], "conversation_id": conversation.id,
            "flow_id": conversation.flow_id.id, "project_id": conversation.project_id.id,
            "owner_id": mailbox.default_owner_id.id if mailbox and not conversation.ppa_message_ids else False,
            "sender_name": first_sender.get("name"), "sender_address": first_sender.get("address"),
            "subject": payload.get("subject"), "body": html_or_text,
            "direction": "incoming", "received_at": IngestionService._email_datetime(payload.get("received_at")),
            "sent_at": IngestionService._email_datetime(payload.get("sent_at")),
            "email_message_id": payload.get("message_id"), "email_in_reply_to": payload.get("in_reply_to"),
            "email_references": json.dumps(payload.get("references", [])), "email_from": json.dumps(payload.get("from", [])),
            "email_to": json.dumps(payload.get("to", [])), "email_cc": json.dumps(payload.get("cc", [])),
            "email_bcc": json.dumps(payload.get("bcc", [])), "email_folder": payload.get("folder"),
            "imap_uid": payload.get("imap_uid"),
            "email_has_attachments": payload.get("has_attachments", False),
            "email_attachment_metadata_json": json.dumps(payload.get("attachments", [])),
            "email_text_body": payload.get("text_body"), "email_html_body": payload.get("html_body"),
            "raw_payload_json": json.dumps(IngestionService._safe_payload(payload.get("raw_payload", payload))),
        }

    @staticmethod
    def _email_datetime(value):
        if not value:
            return False
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except (AttributeError, ValueError):
            return fields.Datetime.to_datetime(value)

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

    def _auto_analyze_message(self, event, message):
        if os.getenv("PPA_AUTO_ANALYZE_MESSAGES", "false").lower() != "true":
            return
        if event.event_type != "email_received" or not (message.email_text_body or message.body):
            return
        if self.env["ppa.ai.analysis"].search_count([("message_id", "=", message.id), ("status", "=", "completed")]):
            return
        try:
            from .intelligence_service import IntelligenceService
            IntelligenceService(self.env).analyze_message(message)
        except Exception as error:
            _logger.warning("PPA ingestion event %s message auto-analysis failed for message %s: %s", event.id, message.id, error)

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
