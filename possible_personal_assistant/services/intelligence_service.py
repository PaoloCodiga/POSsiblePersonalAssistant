import json
import logging
import os

from odoo import fields

from .fake_provider import FakeProvider
from .openai_provider import OpenAiProvider
from .prompts import MESSAGE_ANALYSIS_PROMPT_VERSION

_logger = logging.getLogger(__name__)


class IntelligenceService:
    def __init__(self, env):
        self.env = env

    def _provider(self):
        provider_name = os.getenv("PPA_AI_PROVIDER", "fake")
        return OpenAiProvider() if provider_name == "openai" else FakeProvider()

    def analyze_message(self, message):
        provider = self._provider()
        analysis = self.env["ppa.ai.analysis"].create({"name": "AI analysis: %s" % message.name, "source_type": "message", "message_id": message.id, "provider": provider.name, "model": os.getenv("PPA_OPENAI_MODEL", "") if provider.name == "openai" else "fake", "prompt_version": MESSAGE_ANALYSIS_PROMPT_VERSION, "status": "processing"})
        try:
            result = provider.analyze_message(message)
            self._validate_result(result)
            analysis.write({"status": "completed", "summary": result["summary"], "category": result["category"], "importance": result["importance"], "requires_reply": result["requires_reply"], "requires_action": result["requires_action"], "confidence": result["confidence"], "raw_response_json": json.dumps(result), "processed_at": fields.Datetime.now()})
            message.write({"ai_processed": True, "ai_summary": result["summary"], "ai_category": result["category"], "ai_importance": result["importance"], "ai_confidence": result["confidence"], "requires_reply": result["requires_reply"], "requires_action": result["requires_action"]})
            for action in result.get("suggested_actions", []):
                self.env["ppa.suggested.action"].create({"name": action["title"], "description": action.get("description"), "priority": action.get("priority", "normal"), "due_date": self._due_date(action.get("due_date")), "source_type": "message", "source_message_id": message.id, "ai_analysis_id": analysis.id, "ai_confidence": action.get("confidence", 0), "ai_reason": action.get("reason")})
            return analysis
        except Exception as error:
            _logger.warning("PPA AI analysis %s failed for message %s: %s", analysis.id, message.id, error)
            analysis.write({"status": "failed", "error_message": str(error)[:500], "processed_at": fields.Datetime.now()})
            return analysis

    def _due_date(self, value):
        try:
            return fields.Datetime.to_datetime(value) if value else False
        except (TypeError, ValueError):
            return False

    def _validate_result(self, result):
        categories = dict(self.env["ppa.ai.analysis"]._fields["category"].selection)
        priorities = dict(self.env["ppa.suggested.action"]._fields["priority"].selection)
        if not isinstance(result, dict) or result.get("category") not in categories or result.get("importance") not in priorities or not isinstance(result.get("summary"), str) or not 0 <= float(result.get("confidence", -1)) <= 1:
            raise ValueError("Provider returned an invalid structured analysis result.")
        for action in result.get("suggested_actions", []):
            if not isinstance(action, dict) or not action.get("title") or action.get("priority", "normal") not in priorities:
                raise ValueError("Provider returned an invalid suggested action.")
