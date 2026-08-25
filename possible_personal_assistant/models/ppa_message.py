from odoo import api, fields, models


class PpaMessage(models.Model):
    _name = "ppa.message"
    _description = "PPA Message"
    _inherit = ["mail.thread"]
    _order = "received_at desc, sent_at desc, id desc"

    name = fields.Char(required=True, tracking=True)
    source_id = fields.Many2one("ppa.source", required=True, index=True, tracking=True)
    external_id = fields.Char(index=True, tracking=True)
    conversation_id = fields.Many2one("ppa.conversation", ondelete="set null", index=True, tracking=True)
    sender_name = fields.Char()
    sender_address = fields.Char()
    partner_id = fields.Many2one("res.partner", string="Customer", tracking=True)
    subject = fields.Char(tracking=True)
    body = fields.Html(sanitize=True)
    direction = fields.Selection([("incoming", "Incoming"), ("outgoing", "Outgoing"), ("internal", "Internal")], required=True, default="incoming", tracking=True)
    received_at = fields.Datetime(index=True, tracking=True)
    sent_at = fields.Datetime(index=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, tracking=True)
    project_id = fields.Many2one("project.project", tracking=True)
    raw_payload_json = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    requires_reply = fields.Boolean(tracking=True)
    requires_action = fields.Boolean(tracking=True)
    ai_processed = fields.Boolean(default=False, tracking=True)
    ai_summary = fields.Text()
    ai_category = fields.Char()
    ai_importance = fields.Selection([("low", "Low"), ("normal", "Normal"), ("important", "Important"), ("critical", "Critical")])
    ai_confidence = fields.Float(digits=(3, 2))
    active = fields.Boolean(default=True)

    _source_external_unique = models.Constraint("UNIQUE(source_id, external_id)", "The external message ID must be unique per source.")

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        for message in messages.filtered("conversation_id"):
            timestamp = message.received_at or message.sent_at
            conversation = message.conversation_id
            if timestamp and (not conversation.last_message_at or timestamp > conversation.last_message_at):
                conversation.last_message_at = timestamp
        return messages
