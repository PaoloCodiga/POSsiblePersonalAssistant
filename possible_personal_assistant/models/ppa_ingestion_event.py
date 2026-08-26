import json

from odoo import fields, models


class PpaIngestionEvent(models.Model):
    _name = "ppa.ingestion.event"
    _description = "PPA Ingestion Event"
    _order = "received_at desc, id desc"

    name = fields.Char(required=True)
    source_id = fields.Many2one("ppa.source", required=True, index=True)
    external_event_id = fields.Char(index=True)
    external_object_id = fields.Char(index=True)
    event_type = fields.Selection([
        ("meeting_transcript_ready", "Meeting Transcript Ready"),
        ("meeting_summary_ready", "Meeting Summary Ready"),
        ("meeting_ready", "Meeting Ready"),
        ("manual_import", "Manual Import"),
        ("unknown", "Unknown"),
    ], default="unknown", required=True)
    status = fields.Selection([
        ("received", "Received"), ("processing", "Processing"),
        ("completed", "Completed"), ("failed", "Failed"), ("ignored", "Ignored"),
    ], default="received", required=True, index=True)
    received_at = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    processed_at = fields.Datetime()
    raw_payload_json = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    normalized_payload_json = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    meeting_id = fields.Many2one("ppa.meeting", readonly=True, index=True)
    error_message = fields.Text(readonly=True)
    retry_count = fields.Integer(default=0, readonly=True)
    active = fields.Boolean(default=True)

    _source_event_unique = models.Constraint(
        "UNIQUE(source_id, external_event_id)",
        "The external event ID must be unique per source.",
    )

    def action_retry(self):
        from ..services.ingestion_service import IngestionService
        for event in self:
            IngestionService(self.env).retry_event(event)
        return True
