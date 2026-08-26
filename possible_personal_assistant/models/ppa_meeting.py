from odoo import fields, models


class PpaMeeting(models.Model):
    _name = "ppa.meeting"
    _description = "PPA Meeting"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "started_at desc, id desc"

    name = fields.Char(required=True, tracking=True)
    source_id = fields.Many2one("ppa.source", required=True, index=True, tracking=True)
    external_id = fields.Char(index=True, tracking=True)
    external_url = fields.Char(tracking=True)
    source_created_at = fields.Datetime()
    source_updated_at = fields.Datetime()
    last_ingested_at = fields.Datetime(readonly=True, tracking=True)
    started_at = fields.Datetime(index=True, tracking=True)
    ended_at = fields.Datetime(tracking=True)
    participant_ids = fields.Many2many("res.partner", string="Participants", tracking=True)
    participant_names_json = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, tracking=True)
    project_id = fields.Many2one("project.project", tracking=True)
    transcript = fields.Html(sanitize=True)
    summary = fields.Html(sanitize=True)
    raw_payload_json = fields.Text(groups="possible_personal_assistant.group_ppa_manager")
    ai_processed = fields.Boolean(default=False, tracking=True)
    ai_confidence = fields.Float(digits=(3, 2))
    ai_summary = fields.Text()
    ai_importance = fields.Selection([("low", "Low"), ("normal", "Normal"), ("important", "Important"), ("critical", "Critical")])
    ai_analysis_ids = fields.One2many("ppa.ai.analysis", "meeting_id", string="Analysis History")
    latest_ai_analysis_id = fields.Many2one("ppa.ai.analysis", readonly=True)
    open_question_ids = fields.One2many("ppa.open.question", "meeting_id", string="Open Questions")
    suggested_action_ids = fields.One2many("ppa.suggested.action", "source_meeting_id", string="Related Suggested Actions")
    decision_ids = fields.One2many("ppa.decision", "source_meeting_id", string="Related Decisions")
    active = fields.Boolean(default=True)
    _source_external_unique = models.Constraint("UNIQUE(source_id, external_id)", "The external meeting ID must be unique per source.")

    def action_analyze_with_ai(self):
        from ..services.intelligence_service import IntelligenceService
        for meeting in self:
            analysis = IntelligenceService(self.env).analyze_meeting(meeting)
            if analysis.status == "completed":
                meeting.latest_ai_analysis_id = analysis.id
        return True
