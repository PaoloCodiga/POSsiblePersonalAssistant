import json
import os
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase
from odoo.tools.safe_eval import safe_eval

from ..services.fake_provider import FakeProvider
from ..services.intelligence_service import IntelligenceService
from ..services.ingestion_service import IngestionService
from ..services.mailbox_sync_service import MailboxSyncService
from ..services.imap_mailbox_adapter import ImapMailboxAdapter
from ..services.owner_resolver import resolve_user


class TestPpa(TransactionCase):
    def setUp(self):
        super().setUp()
        self.source = self.env.ref("possible_personal_assistant.source_manual")

    def _email_event(self, event_id, message_id=None, **payload):
        email = {
            "source": "email", "external_event_id": event_id, "event_type": "email_received",
            "payload": {"message_id": message_id, "subject": "Support request", "from": [{"name": "Alice", "address": "alice@example.test"}], "to": [{"address": "paolo.codiga@possible.test"}], "received_at": "2026-08-30T10:00:00Z", "text_body": "Please confirm the deployment."},
        }
        email["payload"].update(payload)
        return email

    def _mailbox(self, **values):
        defaults = {"name": "Test mailbox", "email_address": "mailbox@example.test", "imap_host": "imap.example.test", "username": "mailbox@example.test"}
        defaults.update(values)
        return self.env["ppa.mailbox"].create(defaults)

    def test_mailbox_encrypts_password_without_orm_exposure(self):
        key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        with patch.dict(os.environ, {"PPA_SECRET_ENCRYPTION_KEY": key}):
            mailbox = self._mailbox(password="synthetic-password")
            self.assertNotEqual(mailbox.encrypted_password, "synthetic-password")
            self.assertFalse(mailbox.password)
            self.assertEqual(mailbox.get_password(), "synthetic-password")
            self.assertNotIn("synthetic-password", repr(mailbox.read(["name", "encrypted_password"])))
        with patch.dict(os.environ, {"PPA_SECRET_ENCRYPTION_KEY": "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="}):
            with self.assertRaises(UserError):
                mailbox.get_password()

    def test_mailbox_is_manager_only_and_connection_error_is_sanitized(self):
        user = self.env["res.users"].create({"name": "PPA ordinary", "login": "ppa.ordinary@example.test", "group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(AccessError):
            self.env["ppa.mailbox"].with_user(user).create({"name": "No access", "email_address": "no@example.test", "imap_host": "imap.example.test", "username": "no@example.test"})
        key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        class FailingAdapter:
            def test_connection(self, mailbox, password):
                raise RuntimeError("authentication rejected: %s" % password)
        with patch.dict(os.environ, {"PPA_SECRET_ENCRYPTION_KEY": key}), patch.object(MailboxSyncService, "adapter_factory", FailingAdapter):
            mailbox = self._mailbox(password="synthetic-password")
            self.assertFalse(MailboxSyncService(self.env).test_connection(mailbox))
            self.assertEqual(mailbox.sync_state, "error")
            self.assertNotIn("synthetic-password", mailbox.last_error)

    def test_mailbox_aware_identity_defaults_and_due_selection(self):
        key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        owner = self.env.user
        project = self.env["project.project"].create({"name": "Mailbox project"})
        flow = self.env["ppa.flow"].create({"name": "Mailbox flow", "project_id": project.id})
        with patch.dict(os.environ, {"PPA_SECRET_ENCRYPTION_KEY": key}):
            first_mailbox = self._mailbox(name="First", email_address="first@example.test", password="first", default_owner_id=owner.id, default_flow_id=flow.id)
            second_mailbox = self._mailbox(name="Second", email_address="second@example.test", password="second")
        service = IngestionService(self.env)
        first = service.ingest_event(self._email_event("mailbox-a", "<same@example.test>", mailbox_id=first_mailbox.id))[0]
        duplicate = service.ingest_event(self._email_event("mailbox-b", "<same@example.test>", mailbox_id=first_mailbox.id))[0]
        other = service.ingest_event(self._email_event("mailbox-c", "<same@example.test>", mailbox_id=second_mailbox.id))[0]
        self.assertEqual(first.message_id, duplicate.message_id)
        self.assertNotEqual(first.message_id, other.message_id)
        self.assertEqual(first.message_id.flow_id, flow)
        self.assertEqual(first.message_id.project_id, project)
        self.assertEqual(first.message_id.owner_id, owner)
        manual_flow = self.env["ppa.flow"].create({"name": "Manual flow", "project_id": project.id})
        first.conversation_id.write({"flow_id": manual_flow.id, "operational_state": "waiting"})
        reply = service.ingest_event(self._email_event("mailbox-d", "<reply@example.test>", mailbox_id=first_mailbox.id, in_reply_to="<same@example.test>"))[0]
        self.assertEqual(reply.message_id.flow_id, manual_flow)
        self.assertEqual(reply.message_id.project_id, project)
        self.assertEqual(reply.conversation_id.operational_state, "waiting")
        first_mailbox.last_sync_at = fields.Datetime.now()
        second_mailbox.last_sync_at = False
        due = MailboxSyncService(self.env).due_mailboxes()
        self.assertIn(second_mailbox, due)
        self.assertNotIn(first_mailbox, due)

    def test_imap_bootstrap_and_incremental_sync_are_cursor_safe(self):
        key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        class FakeImap:
            def test_connection(self, mailbox, password):
                if password != "synthetic-password":
                    raise RuntimeError("unexpected fake password")
            def current_position(self, mailbox, password):
                return "100", "9"
            def fetch_new(self, mailbox, password, after_uid):
                if after_uid != "9":
                    raise RuntimeError("unexpected cursor")
                return "100", [
                    ("10", {"message_id": "<uid-10@example.test>", "subject": "First", "from": [{"address": "a@example.test"}], "text_body": "first", "folder": "INBOX"}),
                    ("11", {"message_id": "<uid-11@example.test>", "in_reply_to": "<uid-10@example.test>", "subject": "Re: First", "from": [{"address": "a@example.test"}], "text_body": "second", "folder": "INBOX"}),
                ]
        with patch.dict(os.environ, {"PPA_SECRET_ENCRYPTION_KEY": key}), patch.object(MailboxSyncService, "adapter_factory", FakeImap):
            mailbox = self._mailbox(password="synthetic-password", active=False)
            service = MailboxSyncService(self.env)
            self.assertTrue(service.test_connection(mailbox))
            self.assertTrue(service.bootstrap_mailbox(mailbox))
            self.assertEqual((mailbox.uid_validity, mailbox.last_uid), ("100", "9"))
            self.assertFalse(self.env["ppa.message"].search_count([("mailbox_id", "=", mailbox.id)]))
            self.assertTrue(service.sync_mailbox(mailbox), mailbox.last_error)
            messages = self.env["ppa.message"].search([("mailbox_id", "=", mailbox.id)], order="imap_uid")
            self.assertEqual(messages.mapped("imap_uid"), ["10", "11"])
            self.assertEqual(messages[0].conversation_id, messages[1].conversation_id)
            self.assertEqual(mailbox.last_uid, "11")
            self.assertFalse(self.env["project.task"].search_count([]))
            self.assertFalse(self.env["mail.activity"].search_count([]))

    def test_imap_uidvalidity_mismatch_and_failed_message_do_not_advance_cursor(self):
        key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        class MismatchedImap:
            def fetch_new(self, mailbox, password, after_uid):
                return "changed", []
        with patch.dict(os.environ, {"PPA_SECRET_ENCRYPTION_KEY": key}), patch.object(MailboxSyncService, "adapter_factory", MismatchedImap):
            mailbox = self._mailbox(password="synthetic-password", uid_validity="original", last_uid="4")
            self.assertFalse(MailboxSyncService(self.env).sync_mailbox(mailbox))
            self.assertEqual(mailbox.sync_state, "attention")
            self.assertEqual(mailbox.last_uid, "4")
        class BrokenImap:
            def fetch_new(self, mailbox, password, after_uid):
                return "original", [("5", {"message_id": "<broken@example.test>", "subject": "Broken", "from": [{"address": "a@example.test"}], "text_body": "broken"})]
        with patch.dict(os.environ, {"PPA_SECRET_ENCRYPTION_KEY": key}), patch.object(MailboxSyncService, "adapter_factory", BrokenImap), patch.object(IngestionService, "ingest_event", return_value=(type("Event", (), {"status": "failed"})(), True)):
            self.assertFalse(MailboxSyncService(self.env).sync_mailbox(mailbox))
            self.assertEqual(mailbox.last_uid, "4")
            self.assertEqual(mailbox.sync_state, "error")

    def test_imap_mime_parser_prefers_plain_html_fallback_and_attachment_metadata(self):
        multipart = b"From: A <a@example.test>\r\nTo: B <b@example.test>\r\nMessage-ID: <mime@example.test>\r\nSubject: MIME\r\nMIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=x\r\n\r\n--x\r\nContent-Type: multipart/alternative; boundary=y\r\n\r\n--y\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nUseful plain text\r\n--y\r\nContent-Type: text/html\r\n\r\n<p>Useful <b>HTML</b></p><script>alert(1)</script>\r\n--y--\r\n--x\r\nContent-Type: application/pdf\r\nContent-Disposition: attachment; filename=sample.pdf\r\n\r\nnot-a-binary-download\r\n--x--\r\n"
        parsed = ImapMailboxAdapter.parse_message(multipart, "INBOX")
        self.assertEqual(parsed["text_body"], "Useful plain text")
        self.assertTrue(parsed["has_attachments"])
        self.assertEqual(parsed["attachments"][0]["filename"], "sample.pdf")
        html_only = b"Message-ID: <html@example.test>\r\nContent-Type: text/html\r\n\r\n<p>Useful HTML</p><script>alert(1)</script>"
        fallback = ImapMailboxAdapter.parse_message(html_only, "INBOX")
        self.assertIn("Useful HTML", fallback["html_body"])

    def test_source_uniqueness_and_message_deduplication(self):
        message = self.env["ppa.message"].create({"name": "Test", "source_id": self.source.id, "external_id": "message-1"})
        self.assertTrue(message)
        with self.assertRaises(Exception):
            self.env["ppa.message"].create({"name": "Duplicate", "source_id": self.source.id, "external_id": "message-1"})

    def test_email_message_identity_and_event_idempotency(self):
        service = IngestionService(self.env)
        first, created = service.ingest_event(self._email_event("email-delivery-1", "<mail-1@example.test>"))
        self.assertTrue(created)
        self.assertEqual(first.status, "completed")
        same_event, created = service.ingest_event(self._email_event("email-delivery-1", "<mail-1@example.test>"))
        self.assertFalse(created)
        self.assertEqual(same_event, first)
        richer, created = service.ingest_event(self._email_event("email-delivery-2", "<mail-1@example.test>", cc=[{"address": "team@example.test"}]))
        self.assertTrue(created)
        self.assertEqual(richer.message_id, first.message_id)
        second, created = service.ingest_event(self._email_event("email-delivery-3", "<mail-2@example.test>"))
        self.assertTrue(created)
        self.assertNotEqual(second.message_id, first.message_id)
        fallback_a = service.ingest_event(self._email_event("email-fallback-1", None))[0]
        fallback_b = service.ingest_event(self._email_event("email-fallback-2", None))[0]
        self.assertEqual(fallback_a.message_id, fallback_b.message_id)
        self.assertEqual(self.env["ppa.ingestion.event"].search_count([("source_id.code", "=", "email")]), 5)

    def test_email_conversation_threading_is_explicit_and_conservative(self):
        service = IngestionService(self.env)
        first = service.ingest_event(self._email_event("thread-a", "<a@example.test>", subject="Deployment"))[0]
        reply = service.ingest_event(self._email_event("thread-b", "<b@example.test>", in_reply_to="<a@example.test>", subject="Re: Deployment"))[0]
        referenced = service.ingest_event(self._email_event("thread-c", "<c@example.test>", references=["<missing@example.test>", "<a@example.test>"], subject="Fwd: Deployment"))[0]
        unrelated = service.ingest_event(self._email_event("thread-d", "<d@example.test>", subject="Deployment", **{"from": [{"address": "other@example.test"}]}))[0]
        self.assertEqual(reply.conversation_id, first.conversation_id)
        self.assertEqual(referenced.conversation_id, first.conversation_id)
        self.assertNotEqual(unrelated.conversation_id, first.conversation_id)

    def test_email_flow_and_project_inheritance_and_manual_safety(self):
        service = IngestionService(self.env)
        project = self.env["project.project"].create({"name": "Email project"})
        flow = self.env["ppa.flow"].create({"name": "Certification", "project_id": project.id, "external_reference": "CERT-1"})
        first = service.ingest_event(self._email_event("flow-a", "<flow-a@example.test>"))[0]
        first.conversation_id.write({"flow_id": flow.id, "operational_state": "waiting"})
        reply = service.ingest_event(self._email_event("flow-b", "<flow-b@example.test>", in_reply_to="<flow-a@example.test>"))[0]
        self.assertEqual(reply.message_id.flow_id, flow)
        self.assertEqual(reply.message_id.project_id, project)
        self.assertEqual(reply.conversation_id.project_id, project)
        self.assertEqual(reply.conversation_id.operational_state, "waiting")
        IntelligenceService(self.env).analyze_message(reply.message_id)
        self.assertEqual(reply.conversation_id.flow_id, flow)
        self.assertEqual(reply.conversation_id.project_id, project)
        self.assertEqual(reply.conversation_id.operational_state, "waiting")

    def test_email_html_is_text_safe_and_intelligence_remains_advisory(self):
        event = IngestionService(self.env).ingest_event(self._email_event(
            "html-1", "<html@example.test>", html_body="<p>Please confirm price.</p><script>alert('no')</script>", text_body="",
        ))[0]
        self.assertIn("Please confirm price", event.message_id.email_text_body)
        self.assertNotIn("alert", event.message_id.email_text_body)
        tasks = self.env["project.task"].search_count([])
        activities = self.env["mail.activity"].search_count([])
        analysis = IntelligenceService(self.env).analyze_message(event.message_id)
        self.assertEqual(analysis.status, "completed")
        self.assertTrue(event.message_id.needs_reply)
        self.assertEqual(event.message_id.ai_importance, "important")
        self.assertEqual(self.env["ppa.suggested.action"].search([("ai_analysis_id", "=", analysis.id)]).state, "to_confirm")
        self.assertEqual(self.env["project.task"].search_count([]), tasks)
        self.assertEqual(self.env["mail.activity"].search_count([]), activities)
        self.assertEqual(event.message_id.conversation_id.operational_state, "open")

    def test_email_auto_analysis_is_idempotent_and_reopens_conversation(self):
        with patch.dict(os.environ, {"PPA_AUTO_ANALYZE_MESSAGES": "true"}):
            service = IngestionService(self.env)
            first = service.ingest_event(self._email_event("triage-a", "<triage-a@example.test>", text_body="email_critical_reply please verify"))[0]
            self.assertTrue(first.message_id.ai_processed)
            self.assertEqual(first.message_id.ai_importance, "important")
            self.assertTrue(first.message_id.needs_reply)
            analyses = self.env["ppa.ai.analysis"].search_count([("message_id", "=", first.message_id.id)])
            replay = service.ingest_event(self._email_event("triage-b", "<triage-a@example.test>", text_body="email_critical_reply please verify"))[0]
            self.assertEqual(replay.message_id, first.message_id)
            self.assertEqual(self.env["ppa.ai.analysis"].search_count([("message_id", "=", first.message_id.id)]), analyses)
            first.message_id.action_resolve()
            reply = service.ingest_event(self._email_event("triage-c", "<triage-c@example.test>", in_reply_to="<triage-a@example.test>", text_body="email_no_reply update"))[0]
            self.assertEqual(reply.conversation_id.operational_state, "open")
            manual = IntelligenceService(self.env).analyze_message(first.message_id)
            self.assertEqual(manual.status, "completed")
            self.assertGreater(self.env["ppa.ai.analysis"].search_count([("message_id", "=", first.message_id.id)]), analyses)

    def test_meeting_deduplication(self):
        self.env["ppa.meeting"].create({"name": "Test", "source_id": self.source.id, "external_id": "meeting-1"})
        with self.assertRaises(Exception):
            self.env["ppa.meeting"].create({"name": "Duplicate", "source_id": self.source.id, "external_id": "meeting-1"})

    def test_action_confirmation_and_traceability(self):
        message = self.env["ppa.message"].create({"name": "Source", "source_id": self.source.id})
        action = self.env["ppa.suggested.action"].create({"name": "Follow up", "source_type": "message", "source_message_id": message.id})
        action.action_confirm()
        self.assertEqual(action.state, "confirmed")
        self.assertEqual(action.confirmed_action_type, "activity")
        with self.assertRaises(UserError): action.action_confirm()
        self.assertEqual(action.source_message_id, message)

    def test_action_rejection(self):
        action = self.env["ppa.suggested.action"].create({"name": "Reject me"})
        action.action_reject()
        self.assertEqual(action.state, "rejected")

    def test_fake_intelligence_analysis_and_reanalysis(self):
        message = self.env["ppa.message"].create({"name": "Price confirmation", "source_id": self.source.id, "body": "Paolo, can you verify updated prices today?"})
        task_count = self.env["project.task"].search_count([])
        activity_count = self.env["mail.activity"].search_count([])
        first = IntelligenceService(self.env).analyze_message(message)
        second = IntelligenceService(self.env).analyze_message(message)
        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "completed")
        self.assertTrue(message.ai_processed)
        self.assertEqual(self.env["ppa.ai.analysis"].search_count([("message_id", "=", message.id)]), 2)
        actions = self.env["ppa.suggested.action"].search([("source_message_id", "=", message.id)])
        self.assertEqual(len(actions), 2)
        self.assertTrue(all(action.state == "to_confirm" and action.ai_analysis_id for action in actions))
        self.assertEqual(self.env["project.task"].search_count([]), task_count)
        self.assertEqual(self.env["mail.activity"].search_count([]), activity_count)

    def test_fake_intelligence_no_action_and_failure(self):
        informational = self.env["ppa.message"].create({"name": "Notice", "source_id": self.source.id, "body": "The office will be closed on Monday."})
        analysis = IntelligenceService(self.env).analyze_message(informational)
        self.assertEqual(analysis.status, "completed")
        self.assertFalse(self.env["ppa.suggested.action"].search_count([("source_message_id", "=", informational.id)]))
        failed_message = self.env["ppa.message"].create({"name": "Failure", "source_id": self.source.id, "body": "provider failure"})
        failed = IntelligenceService(self.env).analyze_message(failed_message)
        self.assertEqual(failed.status, "failed")
        self.assertTrue(failed.error_message)
        self.assertFalse(failed_message.ai_processed)

    def test_fake_meeting_full_and_invalid(self):
        meeting = self.env["ppa.meeting"].create({"name": "Meeting", "source_id": self.source.id, "transcript": "meeting_full"})
        tasks = self.env["project.task"].search_count([])
        activities = self.env["mail.activity"].search_count([])
        analysis = IntelligenceService(self.env).analyze_meeting(meeting)
        self.assertEqual(analysis.status, "completed")
        self.assertTrue(meeting.ai_processed)
        self.assertEqual(self.env["ppa.decision"].search_count([("ai_analysis_id", "=", analysis.id)]), 2)
        self.assertEqual(self.env["ppa.suggested.action"].search_count([("ai_analysis_id", "=", analysis.id)]), 3)
        self.assertEqual(self.env["ppa.open.question"].search_count([("ai_analysis_id", "=", analysis.id)]), 2)
        self.assertEqual(self.env["project.task"].search_count([]), tasks)
        self.assertEqual(self.env["mail.activity"].search_count([]), activities)
        invalid = self.env["ppa.meeting"].create({"name": "Invalid", "source_id": self.source.id, "transcript": "meeting_invalid"})
        invalid_analysis = IntelligenceService(self.env).analyze_meeting(invalid)
        self.assertEqual(invalid_analysis.status, "failed")
        self.assertFalse(invalid.ai_processed)

    def test_owner_resolver_is_conservative(self):
        unique = self.env["res.users"].create({"name": "Waheed Unique", "login": "waheed.unique@test.invalid"})
        self.assertEqual(resolve_user(self.env, "  waheed   unique  "), unique)
        self.assertFalse(resolve_user(self.env, "Nobody"))
        first = self.env["res.users"].create({"name": "Ambiguous Owner", "login": "ambiguous.1@test.invalid"})
        second = self.env["res.users"].create({"name": " ambiguous  owner ", "login": "ambiguous.2@test.invalid"})
        self.assertTrue(first and second)
        self.assertFalse(resolve_user(self.env, "AMBIGUOUS OWNER"))
        inactive = self.env["res.users"].create({"name": "Inactive Owner", "login": "inactive.owner@test.invalid", "active": False})
        self.assertTrue(inactive)
        self.assertFalse(resolve_user(self.env, "inactive owner"))

    def test_fake_meeting_scenario_matrix(self):
        scenarios = {"meeting_decisions_only": (1, 0, 0), "meeting_actions_only": (0, 1, 0), "meeting_no_actions": (0, 0, 0), "meeting_failure": (0, 0, 0)}
        for scenario, expected in scenarios.items():
            meeting = self.env["ppa.meeting"].create({"name": scenario, "source_id": self.source.id, "transcript": scenario})
            analysis = IntelligenceService(self.env).analyze_meeting(meeting)
            if scenario == "meeting_failure":
                self.assertEqual(analysis.status, "failed")
                self.assertFalse(meeting.ai_processed)
            else:
                self.assertEqual(analysis.status, "completed")
            self.assertEqual(self.env["ppa.decision"].search_count([("ai_analysis_id", "=", analysis.id)]), expected[0])
            actions = self.env["ppa.suggested.action"].search([("ai_analysis_id", "=", analysis.id)])
            self.assertEqual(len(actions), expected[1])
            self.assertTrue(all(action.state == "to_confirm" and not action.confirmed_task_id and not action.confirmed_activity_id for action in actions))
            self.assertEqual(self.env["ppa.open.question"].search_count([("ai_analysis_id", "=", analysis.id)]), expected[2])

    def test_meeting_reanalysis_and_failed_reanalysis_safety(self):
        meeting = self.env["ppa.meeting"].create({"name": "Reanalysis", "source_id": self.source.id, "transcript": "meeting_full"})
        service = IntelligenceService(self.env)
        first = service.analyze_meeting(meeting)
        first_summary = meeting.ai_summary
        first_counts = (self.env["ppa.decision"].search_count([("ai_analysis_id", "=", first.id)]), self.env["ppa.suggested.action"].search_count([("ai_analysis_id", "=", first.id)]), self.env["ppa.open.question"].search_count([("ai_analysis_id", "=", first.id)]))
        meeting.transcript = "meeting_no_actions"
        second = service.analyze_meeting(meeting)
        self.assertEqual(self.env["ppa.ai.analysis"].search_count([("meeting_id", "=", meeting.id)]), 2)
        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "completed")
        self.assertEqual(first_counts, (2, 3, 2))
        self.assertNotEqual(meeting.ai_summary, first_summary)
        meeting.transcript = "meeting_failure"
        failed = service.analyze_meeting(meeting)
        self.assertEqual(failed.status, "failed")
        self.assertTrue(meeting.ai_processed)
        self.assertEqual(self.env["ppa.decision"].search_count([("ai_analysis_id", "=", first.id)]), 2)
        self.assertEqual(self.env["ppa.suggested.action"].search_count([("ai_analysis_id", "=", first.id)]), 3)
        self.assertEqual(self.env["ppa.open.question"].search_count([("ai_analysis_id", "=", first.id)]), 2)

    def test_meeting_generated_owner_resolution_matrix(self):
        scenarios = [
            (
                "unique",
                "  Owner   Unique ",
                {"name": "Owner Unique", "login": "owner.unique@test.invalid"},
                None,
                True,
            ),
            (
                "ambiguous",
                "Owner Ambiguous",
                {"name": "Owner Ambiguous", "login": "owner.ambiguous.1@test.invalid"},
                {"name": " owner  ambiguous ", "login": "owner.ambiguous.2@test.invalid"},
                False,
            ),
            ("missing", "Owner Missing", None, None, False),
            (
                "inactive",
                "Owner Inactive",
                {
                    "name": "Owner Inactive",
                    "login": "owner.inactive@test.invalid",
                    "active": False,
                },
                None,
                False,
            ),
        ]

        for label, owner_text, first_user, second_user, expected in scenarios:
            user = (
                self.env["res.users"].create(first_user)
                if first_user
                else self.env["res.users"]
            )
            if second_user:
                self.env["res.users"].create(second_user)

            payload = {
                "summary": "Owner resolution test",
                "importance": "normal",
                "confidence": 0.9,
                "decisions": [
                    {
                        "title": "Decision",
                        "responsible_user": owner_text,
                        "confidence": 0.9,
                    }
                ],
                "suggested_actions": [
                    {
                        "title": "Action",
                        "suggested_user": owner_text,
                        "priority": "normal",
                        "confidence": 0.9,
                    }
                ],
                "open_questions": [
                    {
                        "question": "Question",
                        "owner": owner_text,
                        "importance": "normal",
                        "confidence": 0.9,
                    }
                ],
            }
            meeting = self.env["ppa.meeting"].create({"name": "Owner %s" % label, "source_id": self.source.id})
            task_count = self.env["project.task"].search_count([])
            activity_count = self.env["mail.activity"].search_count([])
            with patch.object(FakeProvider, "analyze_meeting", return_value=payload):
                analysis = IntelligenceService(self.env).analyze_meeting(meeting)

            self.assertEqual(analysis.status, "completed", "Meeting analysis %s" % label)
            action = self.env["ppa.suggested.action"].search([("ai_analysis_id", "=", analysis.id)])
            decision = self.env["ppa.decision"].search([("ai_analysis_id", "=", analysis.id)])
            question = self.env["ppa.open.question"].search([("ai_analysis_id", "=", analysis.id)])

            self.assertEqual(len(action), 1, "Suggested Action %s" % label)
            self.assertEqual(len(decision), 1, "Decision %s" % label)
            self.assertEqual(len(question), 1, "Open Question %s" % label)

            self.assertEqual(bool(action.suggested_user_id), expected, "Suggested Action %s" % label)
            self.assertEqual(bool(decision.responsible_user_id), expected, "Decision %s" % label)
            self.assertEqual(bool(question.suggested_user_id), expected, "Open Question %s" % label)
            self.assertEqual(action.suggested_user_text, owner_text, "Suggested Action raw owner %s" % label)
            self.assertEqual(decision.responsible_user_text, owner_text, "Decision raw owner %s" % label)
            self.assertEqual(question.suggested_user_text, owner_text, "Open Question raw owner %s" % label)

            if expected:
                self.assertEqual(action.suggested_user_id, user, "Suggested Action %s" % label)
                self.assertEqual(decision.responsible_user_id, user, "Decision %s" % label)
                self.assertEqual(question.suggested_user_id, user, "Open Question %s" % label)

            self.assertEqual(action.state, "to_confirm", "Suggested Action state %s" % label)
            self.assertFalse(action.confirmed_task_id, "Suggested Action task %s" % label)
            self.assertFalse(action.confirmed_activity_id, "Suggested Action activity %s" % label)
            self.assertEqual(self.env["project.task"].search_count([]), task_count, "Task count %s" % label)
            self.assertEqual(self.env["mail.activity"].search_count([]), activity_count, "Activity count %s" % label)

    def test_plaud_ingestion_idempotency_and_merge(self):
        service = IngestionService(self.env)
        transcript_event = {
            "source": "plaud", "external_id": "recording-test-1",
            "external_event_id": "event-transcript-1",
            "event_type": "meeting_transcript_ready", "name": "Plaud Test",
            "transcript": "Useful transcript", "participants": [{"name": "Unknown Speaker"}],
        }
        event, created = service.ingest_event(transcript_event)
        self.assertTrue(created)
        self.assertEqual(event.status, "completed")
        self.assertEqual(event.meeting_id.external_id, "recording-test-1")
        self.assertEqual(event.meeting_id.transcript, "<p>Useful transcript</p>")
        duplicate, created = service.ingest_event(transcript_event)
        self.assertFalse(created)
        self.assertEqual(duplicate, event)
        summary_event = dict(transcript_event, external_event_id="event-summary-1",
                             event_type="meeting_summary_ready", summary="Useful summary",
                             transcript="")
        summary_event, created = service.ingest_event(summary_event)
        self.assertTrue(created)
        self.assertEqual(summary_event.meeting_id, event.meeting_id)
        self.assertEqual(event.meeting_id.summary, "<p>Useful summary</p>")
        self.assertEqual(event.meeting_id.transcript, "<p>Useful transcript</p>")
        self.assertFalse(self.env["ppa.ai.analysis"].search_count([
            ("meeting_id", "=", event.meeting_id.id)
        ]))
        self.assertEqual(self.env["ppa.ingestion.event"].search_count([
            ("external_object_id", "=", "recording-test-1")]), 2)

    def test_plaud_create_time_identity_ignores_mutable_meeting_fields(self):
        service = IngestionService(self.env)
        create_time = "2026-08-28T10:15:30Z"
        base = {
            "source": "plaud", "create_time": create_time,
            "event_type": "meeting_ready", "name": "Original title",
            "transcript": "Original transcript", "summary": "Original summary",
            "participants": [{"name": "Alex"}],
        }
        first, created = service.ingest_event(dict(base, external_event_id="create-time-base"))
        self.assertTrue(created)
        self.assertEqual(first.status, "completed")
        self.assertTrue(first.meeting_id.external_id.startswith("plaud-created-"))

        changes = (
            ("title", {"name": "Renamed meeting"}),
            ("transcript", {"transcript": "Changed transcript"}),
            ("summary", {"summary": "Changed summary"}),
            ("participants", {"participants": [{"name": "Blair"}]}),
        )
        for label, changed_values in changes:
            event, created = service.ingest_event(dict(
                base,
                create_time="2026-08-28T12:15:30+02:00",
                external_event_id="create-time-{}".format(label),
                **changed_values
            ))
            self.assertTrue(created)
            self.assertEqual(event.meeting_id, first.meeting_id, label)

        other, created = service.ingest_event(dict(
            base, create_time="2026-08-28T10:15:31Z", external_event_id="create-time-other"
        ))
        self.assertTrue(created)
        self.assertNotEqual(other.meeting_id, first.meeting_id)
        self.assertEqual(self.env["ppa.ingestion.event"].search_count([
            ("meeting_id", "=", first.meeting_id.id)
        ]), 5)

    def test_plaud_recording_id_precedes_create_time_identity(self):
        event, created = IngestionService(self.env).ingest_event({
            "source": "plaud", "recording_id": "real-plaud-recording-id",
            "create_time": "2026-08-28T10:15:30Z", "external_event_id": "real-id-event",
            "event_type": "meeting_ready",
        })
        self.assertTrue(created)
        self.assertEqual(event.meeting_id.external_id, "real-plaud-recording-id")

    def test_plaud_ingestion_failure_retry_and_auto_analysis(self):
        service = IngestionService(self.env)
        failed, created = service.ingest_event({
            "source": "plaud", "external_event_id": "event-invalid-1",
            "event_type": "meeting_ready",
        })
        self.assertTrue(created)
        self.assertEqual(failed.status, "failed")
        self.assertTrue(failed.error_message)
        failed.normalized_payload_json = '{"source":"plaud","external_id":"retry-1","external_event_id":"event-invalid-1","event_type":"meeting_ready","name":"Retry","transcript":"meeting_no_actions"}'
        failed.action_retry()
        self.assertEqual(failed.status, "completed")
        self.assertEqual(failed.retry_count, 1)
        tasks = self.env["project.task"].search_count([])
        activities = self.env["mail.activity"].search_count([])
        event, created = service.ingest_event({
            "source": "plaud", "external_id": "ready-1",
            "external_event_id": "event-ready-1", "event_type": "meeting_ready",
            "transcript": "meeting_full",
        })
        self.assertTrue(created)
        analyses = self.env["ppa.ai.analysis"].search([("meeting_id", "=", event.meeting_id.id)])
        self.assertFalse(analyses)
        self.assertEqual(self.env["project.task"].search_count([]), tasks)
        self.assertEqual(self.env["mail.activity"].search_count([]), activities)
        duplicate, created = service.ingest_event({
            "source": "plaud", "external_id": "ready-1", "external_event_id": "event-ready-1",
            "event_type": "meeting_ready", "transcript": "meeting_full",
        })
        self.assertFalse(created)
        self.assertEqual(duplicate, event)
        self.assertFalse(self.env["ppa.ai.analysis"].search_count([("meeting_id", "=", event.meeting_id.id)]))

    def test_plaud_partial_event_never_auto_analyzes(self):
        service = IngestionService(self.env)
        event, created = service.ingest_event({
            "source": "plaud", "external_id": "partial-1",
            "external_event_id": "event-partial-1",
            "event_type": "meeting_transcript_ready", "transcript": "meeting_full",
        })
        self.assertTrue(created)
        self.assertEqual(event.status, "completed")
        self.assertFalse(self.env["ppa.ai.analysis"].search_count([
            ("meeting_id", "=", event.meeting_id.id)
        ]))

    def test_ingestion_raw_payload_scrubs_credentials(self):
        event, created = IngestionService(self.env).ingest_event({
            "source": "plaud", "external_id": "scrubbed-recording-1",
            "external_event_id": "scrubbed-event-1",
            "event_type": "meeting_transcript_ready",
            "raw_payload": {
                "authorization": "regression-secret",
                "x-api-key": "regression-secret",
                "api_key": "regression-secret",
                "token": "regression-secret",
                "access_token": "regression-secret",
                "headers": {"X-PPA-API-Key": "regression-secret"},
                "nested": {"x-api-key": "regression-secret", "safe": "retained"},
            },
        })
        self.assertTrue(created)
        stored = json.loads(event.raw_payload_json)
        self.assertEqual(stored, {"nested": {"safe": "retained"}})
        self.assertNotIn("regression-secret", event.raw_payload_json)

    def test_plaud_summary_first_merges_transcript_and_participants(self):
        service = IngestionService(self.env)
        summary, created = service.ingest_event({
            "source": "plaud", "external_id": "recording-summary-first",
            "external_event_id": "event-summary-first", "event_type": "meeting_summary_ready",
            "name": "Plaud summary first", "summary": "Useful summary",
            "participants": [{"name": "Alex"}],
        })
        self.assertTrue(created)
        transcript, created = service.ingest_event({
            "source": "plaud", "external_id": "recording-summary-first",
            "external_event_id": "event-transcript-second", "event_type": "meeting_transcript_ready",
            "transcript": "Useful transcript", "summary": "",
            "participants": [{"name": "Blair"}],
        })
        self.assertTrue(created)
        meeting = transcript.meeting_id
        self.assertEqual(meeting, summary.meeting_id)
        self.assertEqual(meeting.summary, "<p>Useful summary</p>")
        self.assertEqual(meeting.transcript, "<p>Useful transcript</p>")
        self.assertEqual(json.loads(meeting.participant_names_json), ["Alex", "Blair"])
        duplicate, created = service.ingest_event({
            "source": "plaud", "external_id": "recording-summary-first",
            "external_event_id": "event-summary-first", "event_type": "meeting_summary_ready",
            "summary": "Useful summary",
        })
        self.assertFalse(created)
        self.assertEqual(duplicate, summary)

    def test_plaud_auto_analysis_is_eligible_and_idempotent(self):
        service = IngestionService(self.env)
        tasks = self.env["project.task"].search_count([])
        activities = self.env["mail.activity"].search_count([])
        with patch.dict(os.environ, {"PPA_AUTO_ANALYZE_MEETINGS": "true"}):
            partial, created = service.ingest_event({
                "source": "plaud", "external_id": "auto-partial-1",
                "external_event_id": "auto-partial-event-1",
                "event_type": "meeting_transcript_ready", "transcript": "meeting_full",
            })
            self.assertTrue(created)
            self.assertFalse(self.env["ppa.ai.analysis"].search_count([
                ("meeting_id", "=", partial.meeting_id.id)
            ]))
            event, created = service.ingest_event({
                "source": "plaud", "external_id": "auto-ready-1",
                "external_event_id": "auto-ready-event-1", "event_type": "meeting_ready",
                "transcript": "meeting_full",
            })
            self.assertTrue(created)
            analyses = self.env["ppa.ai.analysis"].search([("meeting_id", "=", event.meeting_id.id)])
            self.assertEqual(len(analyses), 1)
            duplicate, created = service.ingest_event({
                "source": "plaud", "external_id": "auto-ready-1",
                "external_event_id": "auto-ready-event-1", "event_type": "meeting_ready",
                "transcript": "meeting_full",
            })
        self.assertFalse(created)
        self.assertEqual(duplicate, event)
        self.assertEqual(self.env["ppa.ai.analysis"].search_count([
            ("meeting_id", "=", event.meeting_id.id)
        ]), 1)
        self.assertEqual(self.env["project.task"].search_count([]), tasks)
        self.assertEqual(self.env["mail.activity"].search_count([]), activities)

    def test_global_work_queue_lifecycle_context_and_sources(self):
        project = self.env["project.project"].create({"name": "Global work project"})
        flow = self.env["ppa.flow"].create({"name": "Global work flow", "project_id": project.id})
        message = self.env["ppa.message"].create({
            "name": "Incoming work email", "source_id": self.source.id,
            "flow_id": flow.id, "direction": "incoming",
        })
        meeting = self.env["ppa.meeting"].create({
            "name": "Work meeting", "source_id": self.source.id, "flow_id": flow.id,
        })
        email_action = self.env["ppa.suggested.action"].create({
            "name": "Reply to email", "source_type": "message",
            "source_message_id": message.id, "priority": "critical",
            "suggested_user_id": self.env.user.id,
        })
        meeting_action = self.env["ppa.suggested.action"].create({
            "name": "Follow up meeting", "source_type": "meeting",
            "source_meeting_id": meeting.id, "priority": "important",
        })
        self.assertEqual(email_action.source_category, "email")
        self.assertEqual(meeting_action.source_category, "meeting")
        self.assertEqual(email_action.flow_id, flow)
        self.assertEqual(meeting_action.flow_id, flow)
        self.assertEqual(email_action.project_id, project)
        self.assertEqual(meeting_action.project_id, project)
        self.assertEqual(email_action.priority_rank, 0)
        self.assertEqual(meeting_action.priority_rank, 1)
        test_actions = email_action | meeting_action
        global_domain = safe_eval(
            self.env.ref("possible_personal_assistant.ppa_global_work_queue_action").domain,
            {"uid": self.env.uid},
        )
        my_work_domain = safe_eval(
            self.env.ref("possible_personal_assistant.ppa_my_work_queue_action").domain,
            {"uid": self.env.uid},
        )
        to_confirm_domain = safe_eval(
            self.env.ref("possible_personal_assistant.ppa_to_confirm_action").domain,
            {"uid": self.env.uid},
        )
        self.assertEqual(
            self.env["ppa.suggested.action"].search(global_domain + [("id", "in", test_actions.ids)]),
            test_actions,
        )
        self.assertEqual(
            self.env["ppa.suggested.action"].search(my_work_domain + [("id", "in", test_actions.ids)]),
            test_actions,
        )
        self.assertEqual(
            self.env["ppa.suggested.action"].search(to_confirm_domain + [("id", "in", test_actions.ids)]),
            test_actions,
        )
        tasks_before = self.env["project.task"].search_count([])
        activities_before = self.env["mail.activity"].search_count([])
        email_action.action_confirm()
        self.assertEqual(email_action.state, "confirmed")
        self.assertEqual(self.env["project.task"].search_count([]), tasks_before + 1)
        self.assertEqual(self.env["mail.activity"].search_count([]), activities_before)
        email_action.action_start()
        email_action.action_set_waiting()
        self.assertEqual(email_action.state, "waiting")
        self.assertTrue(email_action.waiting_since)
        waiting_domain = safe_eval(
            self.env.ref("possible_personal_assistant.ppa_waiting_work_action").domain,
            {"uid": self.env.uid},
        )
        self.assertEqual(
            self.env["ppa.suggested.action"].search(waiting_domain + [("id", "in", test_actions.ids)]),
            email_action,
        )
        email_action.action_resume()
        email_action.action_mark_done()
        self.assertEqual(email_action.state, "completed")
        self.assertEqual(
            self.env["ppa.suggested.action"].search(global_domain + [("id", "in", test_actions.ids)]),
            meeting_action,
        )
        email_action.action_reopen()
        self.assertEqual(email_action.state, "to_confirm")
        meeting_action.action_reject()
        self.assertEqual(meeting_action.state, "rejected")
        self.assertFalse(self.env["ppa.suggested.action"].search([
            ("state", "not in", ("completed", "rejected")), ("id", "=", meeting_action.id)
        ]))
