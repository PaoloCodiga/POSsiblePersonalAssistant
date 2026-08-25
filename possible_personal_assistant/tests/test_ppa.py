from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo import fields

from ..services.intelligence_service import IntelligenceService


class TestPpa(TransactionCase):
    def setUp(self):
        super().setUp()
        self.source = self.env.ref("possible_personal_assistant.source_manual")

    def test_source_uniqueness_and_message_deduplication(self):
        message = self.env["ppa.message"].create({"name": "Test", "source_id": self.source.id, "external_id": "message-1"})
        self.assertTrue(message)
        with self.assertRaises(Exception):
            self.env["ppa.message"].create({"name": "Duplicate", "source_id": self.source.id, "external_id": "message-1"})

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
