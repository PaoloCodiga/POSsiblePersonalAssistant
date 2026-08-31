from odoo import api, fields, models


class PpaMessage(models.Model):
    _name = "ppa.message"
    _description = "PPA Message"
    _inherit = ["mail.thread"]
    _order = "importance_rank asc, received_at desc, sent_at desc, id desc"

    name = fields.Char(required=True, tracking=True)
    source_id = fields.Many2one("ppa.source", required=True, index=True, tracking=True)
    mailbox_id = fields.Many2one("ppa.mailbox", ondelete="set null", index=True, tracking=True)
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
    flow_id = fields.Many2one("ppa.flow", ondelete="set null", index=True, tracking=True)
    project_id = fields.Many2one("project.project", ondelete="set null", tracking=True)
    owner_id = fields.Many2one("res.users", ondelete="set null", tracking=True)
    operational_state = fields.Selection(related="conversation_id.operational_state", string="Operational State", readonly=False, store=True, index=True)
    email_message_id = fields.Char(index=True, tracking=True)
    email_in_reply_to = fields.Char(index=True, tracking=True)
    email_references = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    email_from = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    email_to = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    email_cc = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    email_bcc = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    email_folder = fields.Char(tracking=True)
    imap_uid = fields.Char(index=True, tracking=True)
    email_has_attachments = fields.Boolean(default=False, tracking=True)
    email_attachment_metadata_json = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    email_text_body = fields.Text()
    email_html_body = fields.Html(sanitize=True)
    raw_payload_json = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    requires_reply = fields.Boolean(string="Requires Reply", tracking=True)
    needs_reply = fields.Boolean(related="requires_reply", string="Needs Reply", readonly=False)
    requires_action = fields.Boolean(tracking=True)
    ai_processed = fields.Boolean(default=False, tracking=True)
    ai_summary = fields.Text()
    ai_category = fields.Char()
    ai_importance = fields.Selection([("low", "Low"), ("normal", "Normal"), ("important", "Important"), ("critical", "Critical")])
    ai_confidence = fields.Float(digits=(3, 2))
    ai_reasoning_summary = fields.Char()
    importance_rank = fields.Integer(compute="_compute_importance_rank", store=True, index=True)
    ai_analysis_ids = fields.One2many("ppa.ai.analysis", "message_id", string="Analysis History")
    latest_ai_analysis_id = fields.Many2one("ppa.ai.analysis", string="Latest AI Analysis", readonly=True)
    suggested_action_ids = fields.One2many("ppa.suggested.action", "source_message_id", string="Related Suggested Actions")
    active = fields.Boolean(default=True)

    _source_external_unique = models.Constraint("UNIQUE(source_id, external_id)", "The external message ID must be unique per source.")

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            conversation = self.env["ppa.conversation"].browse(values.get("conversation_id"))
            if conversation:
                values.setdefault("flow_id", conversation.flow_id.id)
                if conversation.flow_id and conversation.flow_id.project_id:
                    values["project_id"] = conversation.flow_id.project_id.id
                else:
                    values.setdefault("project_id", conversation.project_id.id)
        messages = super().create(vals_list)
        for message in messages.filtered("conversation_id"):
            timestamp = message.received_at or message.sent_at
            conversation = message.conversation_id
            if timestamp and (not conversation.last_message_at or timestamp > conversation.last_message_at):
                conversation.last_message_at = timestamp
            if message.direction == "incoming" and conversation.operational_state in ("resolved", "ignored"):
                conversation.operational_state = "open"
        return messages

    @api.depends("ai_importance")
    def _compute_importance_rank(self):
        ranks = {"critical": 0, "important": 1, "normal": 2, "low": 3}
        for message in self:
            message.importance_rank = ranks.get(message.ai_importance, 4)

    def action_analyze_with_ai(self):
        from ..services.intelligence_service import IntelligenceService
        for message in self:
            analysis = IntelligenceService(self.env).analyze_message(message)
            if analysis.status == "completed":
                message.latest_ai_analysis_id = analysis.id
        return True

    def _set_conversation_state(self, state):
        for message in self.filtered("conversation_id"):
            message.conversation_id.operational_state = state
        return True

    def action_start_work(self): return self._set_conversation_state("in_progress")
    def action_waiting(self): return self._set_conversation_state("waiting")
    def action_resolve(self): return self._set_conversation_state("resolved")
    def action_ignore(self): return self._set_conversation_state("ignored")
    def action_reopen(self): return self._set_conversation_state("open")
