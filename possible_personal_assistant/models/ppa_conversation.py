from odoo import api, fields, models


class PpaConversation(models.Model):
    _name = "ppa.conversation"
    _description = "PPA Conversation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "last_message_at desc, id desc"

    name = fields.Char(required=True, tracking=True)
    source_id = fields.Many2one("ppa.source", required=True, index=True, tracking=True)
    mailbox_id = fields.Many2one("ppa.mailbox", ondelete="set null", index=True, tracking=True)
    external_id = fields.Char(index=True, tracking=True)
    partner_ids = fields.Many2many("res.partner", string="Participants", tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, tracking=True)
    flow_id = fields.Many2one("ppa.flow", ondelete="set null", index=True, tracking=True)
    project_id = fields.Many2one("project.project", ondelete="set null", tracking=True)
    operational_state = fields.Selection([
        ("open", "Open"), ("in_progress", "In Progress"), ("waiting", "Waiting"),
        ("resolved", "Resolved"), ("ignored", "Ignored"),
    ], default="open", required=True, index=True, tracking=True)
    last_message_at = fields.Datetime(index=True, tracking=True)
    ppa_message_ids = fields.One2many("ppa.message", "conversation_id", string="Messages")
    active = fields.Boolean(default=True)

    _source_external_unique = models.Constraint("UNIQUE(source_id, external_id)", "The external conversation ID must be unique per source.")

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            flow = self.env["ppa.flow"].browse(values.get("flow_id"))
            if flow and flow.project_id:
                values["project_id"] = flow.project_id.id
        return super().create(vals_list)

    def write(self, values):
        if "flow_id" in values:
            flow = self.env["ppa.flow"].browse(values["flow_id"])
            if flow and flow.project_id:
                values = dict(values, project_id=flow.project_id.id)
        return super().write(values)
