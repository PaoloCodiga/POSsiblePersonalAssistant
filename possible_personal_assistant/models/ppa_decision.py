from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PpaDecision(models.Model):
    _name = "ppa.decision"
    _description = "PPA Decision"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "decision_date desc, id desc"

    name = fields.Char(required=True, tracking=True)
    description = fields.Html()
    decision_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, tracking=True)
    project_id = fields.Many2one("project.project", tracking=True)
    responsible_user_id = fields.Many2one("res.users", tracking=True)
    source_type = fields.Selection([("message", "Message"), ("meeting", "Meeting"), ("manual", "Manual")], default="manual", required=True, tracking=True)
    source_message_id = fields.Many2one("ppa.message", ondelete="restrict", tracking=True)
    source_meeting_id = fields.Many2one("ppa.meeting", ondelete="restrict", tracking=True)
    ai_analysis_id = fields.Many2one("ppa.ai.analysis", ondelete="restrict", readonly=True)
    active = fields.Boolean(default=True)

    @api.constrains("source_type", "source_message_id", "source_meeting_id")
    def _check_source(self):
        for record in self:
            valid = ((record.source_type == "manual" and not record.source_message_id and not record.source_meeting_id) or
                     (record.source_type == "message" and record.source_message_id and not record.source_meeting_id) or
                     (record.source_type == "meeting" and record.source_meeting_id and not record.source_message_id))
            if not valid:
                raise ValidationError(_("The source type must match exactly one source record."))
