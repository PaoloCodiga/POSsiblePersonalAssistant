from odoo import fields, models


class PpaFlow(models.Model):
    _name = "ppa.flow"
    _description = "PPA Flow"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "last_activity_at desc, id desc"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ("open", "Open"), ("in_progress", "In Progress"), ("waiting", "Waiting"),
        ("resolved", "Resolved"), ("ignored", "Ignored"),
    ], default="open", required=True, index=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, tracking=True)
    project_id = fields.Many2one("project.project", ondelete="set null", tracking=True)
    owner_id = fields.Many2one("res.users", ondelete="set null", tracking=True)
    priority = fields.Selection([
        ("low", "Low"), ("normal", "Normal"), ("important", "Important"), ("critical", "Critical"),
    ], default="normal", required=True, index=True, tracking=True)
    description = fields.Html(sanitize=True)
    external_reference = fields.Char(index=True, tracking=True)
    first_activity_at = fields.Datetime(index=True, tracking=True)
    last_activity_at = fields.Datetime(index=True, tracking=True)
    conversation_ids = fields.One2many("ppa.conversation", "flow_id", string="Conversations")
    work_item_ids = fields.One2many("ppa.suggested.action", "flow_id", string="Work Items")
