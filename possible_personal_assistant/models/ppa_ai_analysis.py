from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PpaAiAnalysis(models.Model):
    _name = "ppa.ai.analysis"
    _description = "PPA AI Analysis"
    _inherit = ["mail.thread"]
    _order = "processed_at desc, id desc"

    name = fields.Char(required=True, default="AI Message Analysis")
    source_type = fields.Selection([("message", "Message"), ("meeting", "Meeting")], required=True, default="message")
    message_id = fields.Many2one("ppa.message", ondelete="restrict", index=True)
    meeting_id = fields.Many2one("ppa.meeting", ondelete="restrict", index=True)
    provider = fields.Char(required=True)
    model = fields.Char()
    prompt_version = fields.Char(required=True)
    status = fields.Selection([("pending", "Pending"), ("processing", "Processing"), ("completed", "Completed"), ("failed", "Failed")], required=True, default="pending", tracking=True)
    summary = fields.Text()
    category = fields.Selection([("customer_request", "Customer Request"), ("technical", "Technical"), ("sales", "Sales"), ("administrative", "Administrative"), ("finance", "Finance"), ("project", "Project"), ("internal", "Internal"), ("notification", "Notification"), ("spam", "Spam"), ("other", "Other")])
    importance = fields.Selection([("low", "Low"), ("normal", "Normal"), ("important", "Important"), ("critical", "Critical")])
    requires_reply = fields.Boolean()
    requires_action = fields.Boolean()
    confidence = fields.Float(digits=(3, 2))
    raw_response_json = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    processed_at = fields.Datetime()
    error_message = fields.Char()
    suggested_action_ids = fields.One2many("ppa.suggested.action", "ai_analysis_id")
    active = fields.Boolean(default=True)

    @api.constrains("source_type", "message_id", "meeting_id", "confidence")
    def _check_source_and_confidence(self):
        for record in self:
            valid_source = ((record.source_type == "message" and record.message_id and not record.meeting_id) or (record.source_type == "meeting" and record.meeting_id and not record.message_id))
            if not valid_source:
                raise ValidationError(_("The analysis source type must match exactly one source record."))
            if not 0 <= record.confidence <= 1:
                raise ValidationError(_("Confidence must be between 0.0 and 1.0."))
