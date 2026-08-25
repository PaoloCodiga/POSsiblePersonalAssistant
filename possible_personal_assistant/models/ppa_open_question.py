from odoo import fields, models


class PpaOpenQuestion(models.Model):
    _name = "ppa.open.question"
    _description = "PPA Open Question"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True)
    description = fields.Text()
    meeting_id = fields.Many2one("ppa.meeting", required=True, ondelete="restrict")
    ai_analysis_id = fields.Many2one("ppa.ai.analysis", required=True, ondelete="restrict")
    suggested_user_id = fields.Many2one("res.users")
    suggested_user_text = fields.Char()
    importance = fields.Selection([("low", "Low"), ("normal", "Normal"), ("important", "Important"), ("critical", "Critical")], default="normal")
    confidence = fields.Float(digits=(3, 2))
    state = fields.Selection([("open", "Open"), ("resolved", "Resolved"), ("dismissed", "Dismissed")], default="open")
    company_id = fields.Many2one("res.company")
    project_id = fields.Many2one("project.project")
    active = fields.Boolean(default=True)
