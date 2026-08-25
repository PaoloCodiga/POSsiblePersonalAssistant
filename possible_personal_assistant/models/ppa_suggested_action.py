from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PpaSuggestedAction(models.Model):
    _name = "ppa.suggested.action"
    _description = "PPA Suggested Action"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, due_date asc, id desc"

    name = fields.Char(required=True, tracking=True)
    description = fields.Html()
    suggested_user_id = fields.Many2one("res.users", string="Assigned User", default=lambda self: self.env.user, tracking=True)
    partner_id = fields.Many2one("res.partner", string="Customer", tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, tracking=True)
    project_id = fields.Many2one("project.project", tracking=True)
    priority = fields.Selection([("low", "Low"), ("normal", "Normal"), ("important", "Important"), ("critical", "Critical")], default="normal", required=True, tracking=True)
    state = fields.Selection([("to_confirm", "To Confirm"), ("confirmed", "Confirmed"), ("in_progress", "In Progress"), ("completed", "Completed"), ("rejected", "Rejected")], default="to_confirm", required=True, tracking=True)
    due_date = fields.Datetime(index=True, tracking=True)
    source_type = fields.Selection([("message", "Message"), ("meeting", "Meeting"), ("manual", "Manual")], default="manual", required=True, tracking=True)
    source_message_id = fields.Many2one("ppa.message", ondelete="restrict", tracking=True)
    source_meeting_id = fields.Many2one("ppa.meeting", ondelete="restrict", tracking=True)
    ai_confidence = fields.Float(digits=(3, 2))
    ai_reason = fields.Text()
    ai_analysis_id = fields.Many2one("ppa.ai.analysis", ondelete="restrict", readonly=True)
    confirmed_action_type = fields.Selection([("activity", "Activity"), ("task", "Task")], readonly=True, tracking=True)
    confirmed_activity_id = fields.Many2one("mail.activity", readonly=True, ondelete="set null")
    confirmed_task_id = fields.Many2one("project.task", readonly=True, ondelete="set null")
    active = fields.Boolean(default=True)

    @api.constrains("source_type", "source_message_id", "source_meeting_id")
    def _check_source(self):
        for record in self:
            valid = ((record.source_type == "manual" and not record.source_message_id and not record.source_meeting_id) or
                     (record.source_type == "message" and record.source_message_id and not record.source_meeting_id) or
                     (record.source_type == "meeting" and record.source_meeting_id and not record.source_message_id))
            if not valid:
                raise ValidationError(_("The source type must match exactly one source record."))

    def action_confirm(self):
        for record in self:
            if record.state != "to_confirm" or record.confirmed_action_type:
                raise UserError(_("Only an unconfirmed suggested action can be confirmed."))
            if record.project_id:
                task = self.env["project.task"].create({"name": record.name, "description": record.description, "project_id": record.project_id.id, "user_ids": [(4, record.suggested_user_id.id)] if record.suggested_user_id else []})
                record.write({"state": "confirmed", "confirmed_action_type": "task", "confirmed_task_id": task.id})
            else:
                activity_type = self.env.ref("possible_personal_assistant.ppa_activity_type_follow_up")
                activity = self.env["mail.activity"].create({"activity_type_id": activity_type.id, "summary": record.name, "note": record.description, "user_id": record.suggested_user_id.id or self.env.user.id, "res_model_id": self.env["ir.model"]._get_id("ppa.suggested.action"), "res_id": record.id, "date_deadline": fields.Date.to_date(record.due_date) if record.due_date else fields.Date.context_today(record)})
                record.write({"state": "confirmed", "confirmed_action_type": "activity", "confirmed_activity_id": activity.id})
        return True

    def action_reject(self):
        self.filtered(lambda record: record.state == "to_confirm").write({"state": "rejected"})
        return True

    def action_start(self):
        for record in self:
            if record.state != "confirmed":
                raise UserError(_("Only confirmed actions can be started."))
        self.write({"state": "in_progress"})
        return True

    def action_mark_done(self):
        for record in self:
            if record.state not in ("confirmed", "in_progress"):
                raise UserError(_("Only confirmed or in-progress actions can be completed."))
            if record.confirmed_activity_id:
                record.confirmed_activity_id.action_feedback()
            # Project tasks intentionally retain their project's configured stage.
            record.state = "completed"
        return True

    def action_reopen(self):
        for record in self:
            if record.state not in ("rejected", "completed"):
                raise UserError(_("Only rejected or completed actions can be reopened."))
        self.write({"state": "to_confirm"})
        return True
