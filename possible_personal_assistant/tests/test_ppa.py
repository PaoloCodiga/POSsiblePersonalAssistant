from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


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
