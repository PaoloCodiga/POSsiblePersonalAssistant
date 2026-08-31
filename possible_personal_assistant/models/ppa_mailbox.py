from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.secret_cipher import SecretCipher


class PpaMailbox(models.Model):
    _name = "ppa.mailbox"
    _description = "PPA Mailbox"
    _rec_name = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    email_address = fields.Char(required=True, index=True)
    protocol = fields.Selection([("imap", "IMAP")], required=True, default="imap")
    imap_host = fields.Char(required=True)
    imap_port = fields.Integer(required=True, default=993)
    imap_ssl = fields.Boolean(default=True)
    imap_starttls = fields.Boolean(default=False)
    username = fields.Char(required=True)
    encrypted_password = fields.Text(copy=False, groups="possible_personal_assistant.group_ppa_manager")
    password = fields.Char(string="Password", groups="possible_personal_assistant.group_ppa_manager", compute="_compute_password", inverse="_inverse_password", store=False)
    folder = fields.Char(required=True, default="INBOX")
    poll_interval_minutes = fields.Integer(required=True, default=5)
    last_sync_at = fields.Datetime(readonly=True)
    last_success_at = fields.Datetime(readonly=True)
    last_error = fields.Char(readonly=True)
    sync_state = fields.Selection([("idle", "Idle"), ("ready", "Ready"), ("syncing", "Syncing"), ("attention", "Needs Attention"), ("error", "Error")], default="idle", required=True, readonly=True)
    last_uid = fields.Char(readonly=True, copy=False)
    uid_validity = fields.Char(readonly=True, copy=False)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    default_owner_id = fields.Many2one("res.users", ondelete="set null")
    default_project_id = fields.Many2one("project.project", ondelete="set null")
    default_flow_id = fields.Many2one("ppa.flow", ondelete="set null")

    @api.depends("encrypted_password")
    def _compute_password(self):
        for mailbox in self:
            mailbox.password = False

    def _inverse_password(self):
        # create/write intercept the replacement field; no value is retained in ORM.
        return None

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            password = values.pop("password", False)
            if password:
                values["encrypted_password"] = SecretCipher.encrypt(password)
        return super().create(vals_list)

    def write(self, values):
        values = dict(values)
        password = values.pop("password", False)
        if password:
            values["encrypted_password"] = SecretCipher.encrypt(password)
        return super().write(values)

    def get_password(self):
        self.ensure_one()
        if not self.encrypted_password:
            raise UserError("Mailbox password is not configured.")
        try:
            return SecretCipher.decrypt(self.encrypted_password)
        except ValueError as error:
            raise UserError("Mailbox credential is unavailable.") from error

    def action_test_connection(self):
        from ..services.mailbox_sync_service import MailboxSyncService
        for mailbox in self:
            MailboxSyncService(self.env).test_connection(mailbox)
        return True

    def action_sync_now(self):
        from ..services.mailbox_sync_service import MailboxSyncService
        for mailbox in self:
            MailboxSyncService(self.env).sync_mailbox(mailbox)
        return True

    def action_initialize_current_inbox(self):
        from ..services.mailbox_sync_service import MailboxSyncService
        for mailbox in self:
            MailboxSyncService(self.env).bootstrap_mailbox(mailbox)
        return True

    @api.model
    def cron_sync_due_mailboxes(self):
        from ..services.mailbox_sync_service import MailboxSyncService
        return MailboxSyncService(self.env).run_due_mailboxes()
