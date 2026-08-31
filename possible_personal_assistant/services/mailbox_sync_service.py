import logging
from datetime import timedelta

from odoo import fields

from .imap_mailbox_adapter import ImapMailboxAdapter
from .ingestion_service import IngestionService

_logger = logging.getLogger(__name__)


class MailboxSyncService:
    """Central IMAP synchronization service; mailbox failures remain isolated."""

    adapter_factory = ImapMailboxAdapter

    def __init__(self, env):
        self.env = env

    def due_mailboxes(self, now=None):
        now = now or fields.Datetime.now()
        mailboxes = self.env["ppa.mailbox"].search([("active", "=", True), ("sync_state", "!=", "attention")])
        return mailboxes.filtered(lambda mailbox: not mailbox.last_sync_at or (
            mailbox.last_sync_at + timedelta(minutes=mailbox.poll_interval_minutes) <= now
        ))

    @staticmethod
    def _safe_error(error, secrets=()):
        # Do not include connection/user/password data in persisted diagnostics.
        text = str(error or "Mailbox connection failed.")
        for secret in secrets:
            if secret:
                text = text.replace(str(secret), "[redacted]")
        text = text.replace("\n", " ").replace("\r", " ")
        return "Mailbox operation failed: %s" % text[:180]

    def test_connection(self, mailbox):
        password = False
        try:
            password = mailbox.get_password()
            self.adapter_factory().test_connection(mailbox, password)
            mailbox.write({"sync_state": "ready", "last_success_at": fields.Datetime.now(), "last_error": False})
            return True
        except Exception as error:
            mailbox.write({"sync_state": "error", "last_error": self._safe_error(error, (password,))})
            return False

    def bootstrap_mailbox(self, mailbox):
        password = False
        try:
            password = mailbox.get_password()
            uid_validity, highest_uid = self.adapter_factory().current_position(mailbox, password)
            mailbox.write({"uid_validity": uid_validity, "last_uid": highest_uid, "sync_state": "ready", "last_success_at": fields.Datetime.now(), "last_error": False})
            return True
        except Exception as error:
            mailbox.write({"sync_state": "error", "last_error": self._safe_error(error, (password,))})
            return False

    def _record_failure(self, mailbox, uid, error):
        source = self.env.ref("possible_personal_assistant.source_email")
        event_id = "imap:%s:%s:%s" % (mailbox.id, mailbox.uid_validity or "unknown", uid)
        existing = self.env["ppa.ingestion.event"].search([
            ("source_id", "=", source.id), ("external_event_id", "=", event_id),
        ], limit=1)
        if existing:
            return existing
        return self.env["ppa.ingestion.event"].create({
            "name": "IMAP malformed message %s" % uid, "source_id": source.id, "mailbox_id": mailbox.id,
            "external_event_id": event_id,
            "external_object_id": "email:%s:imap-uid:%s" % (mailbox.id, uid), "imap_uid": str(uid),
            "event_type": "email_received", "status": "failed", "processed_at": fields.Datetime.now(),
            "error_message": self._safe_error(error),
        })

    def sync_mailbox(self, mailbox):
        password = False
        try:
            if not mailbox.uid_validity or mailbox.last_uid is False:
                mailbox.write({"sync_state": "attention", "last_error": "Mailbox bootstrap is required before synchronization."})
                return False
            mailbox.write({"sync_state": "syncing", "last_error": False, "last_sync_at": fields.Datetime.now()})
            password = mailbox.get_password()
            uid_validity, messages = self.adapter_factory().fetch_new(mailbox, password, mailbox.last_uid)
            if uid_validity != mailbox.uid_validity:
                mailbox.write({"sync_state": "attention", "last_error": "IMAP UIDVALIDITY changed; manager re-initialization is required."})
                return False
            for uid, payload in messages:
                try:
                    delivery = {"source": "email", "mailbox_id": mailbox.id, "external_event_id": "imap:%s:%s:%s" % (mailbox.id, uid_validity, uid), "event_type": "email_received", "imap_uid": uid, "payload": dict(payload, mailbox_id=mailbox.id, imap_uid=uid)}
                    event, _created = IngestionService(self.env).ingest_event(delivery)
                    if event.status != "completed":
                        raise RuntimeError("Email ingestion failed.")
                except Exception as error:
                    self._record_failure(mailbox, uid, error)
                    mailbox.write({"sync_state": "error", "last_error": self._safe_error(error, (password,))})
                    return False
                mailbox.write({"last_uid": str(uid)})
            mailbox.write({"sync_state": "ready", "last_success_at": fields.Datetime.now(), "last_error": False})
            return True
        except Exception as error:
            mailbox.write({"sync_state": "error", "last_error": self._safe_error(error, (password,))})
            return False

    def run_due_mailboxes(self):
        for mailbox in self.due_mailboxes():
            try:
                self.sync_mailbox(mailbox)
            except Exception:
                _logger.exception("PPA mailbox %s synchronization failed.", mailbox.id)
        return True
