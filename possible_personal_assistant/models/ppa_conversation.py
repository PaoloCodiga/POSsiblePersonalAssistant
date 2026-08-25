from odoo import fields, models


class PpaConversation(models.Model):
    _name = "ppa.conversation"
    _description = "PPA Conversation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "last_message_at desc, id desc"

    name = fields.Char(required=True, tracking=True)
    source_id = fields.Many2one("ppa.source", required=True, index=True, tracking=True)
    external_id = fields.Char(index=True, tracking=True)
    partner_ids = fields.Many2many("res.partner", string="Participants", tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, tracking=True)
    project_id = fields.Many2one("project.project", tracking=True)
    last_message_at = fields.Datetime(index=True, tracking=True)
    ppa_message_ids = fields.One2many("ppa.message", "conversation_id", string="Messages")
    active = fields.Boolean(default=True)

    _source_external_unique = models.Constraint("UNIQUE(source_id, external_id)", "The external conversation ID must be unique per source.")
