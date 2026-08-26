from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from ..services.fake_provider import FakeProvider
from ..services.intelligence_service import IntelligenceService
from ..services.owner_resolver import resolve_user


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
