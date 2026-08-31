import json
import os
import re
from urllib import error as urlerror
from urllib import request as urlrequest

from .ai_provider import AiProvider
from .prompts import MESSAGE_ANALYSIS_SYSTEM_PROMPT, MEETING_ANALYSIS_SYSTEM_PROMPT


class OpenAiApiError(RuntimeError):
    """A safe, user-visible diagnostic for a failed OpenAI API response."""


class OpenAiProvider(AiProvider):
    name = "openai"

    _IMPORTANCE = ["low", "normal", "important", "critical"]
    _PRIORITY = ["low", "normal", "important", "critical"]

    def analyze_message(self, message):
        content = "Subject: %s\nBody: %s" % (message.subject or "", message.email_text_body or message.body or "")
        return self._analyze(MESSAGE_ANALYSIS_SYSTEM_PROMPT, content, self._message_schema())

    def analyze_meeting(self, meeting):
        participants = ", ".join(meeting.participant_ids.mapped("name"))
        content = "Title: %s\nParticipants: %s\nSummary: %s\nTranscript: %s" % (
            meeting.name or "", participants, meeting.summary or "", meeting.transcript or "",
        )
        return self._analyze(MEETING_ANALYSIS_SYSTEM_PROMPT, content, self._meeting_schema())

    def _analyze(self, instructions, content, schema):
        api_key = os.getenv("PPA_OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OpenAI API key is not configured.")
        model = os.getenv("PPA_OPENAI_MODEL", "gpt-4.1-mini")
        payload = {
            "model": model,
            "instructions": instructions,
            "input": content,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema["name"],
                    "strict": True,
                    "schema": schema["schema"],
                },
            },
        }
        request = urlrequest.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
            method="POST",
        )
        timeout = int(os.getenv("PPA_AI_TIMEOUT_SECONDS", "60"))
        try:
            with urlrequest.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urlerror.HTTPError as error:
            raise OpenAiApiError(self._http_error_message(error)) from None
        return json.loads(self._output_text(result))

    @staticmethod
    def _output_text(result):
        for item in result.get("output", []):
            for part in item.get("content", []):
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    return part["text"]
        raise ValueError("OpenAI Responses API returned no structured output text.")

    @staticmethod
    def _http_error_message(error):
        try:
            body = json.loads(error.read().decode("utf-8", errors="replace"))
            detail = body.get("error", {}) if isinstance(body, dict) else {}
            error_type = detail.get("type") or "http_error"
            message = detail.get("message") or "OpenAI request failed."
        except (UnicodeDecodeError, ValueError, AttributeError):
            error_type, message = "http_error", "OpenAI request failed."
        message = re.sub(r"(?i)(bearer\\s+|sk-)[^\\s,;]+", r"\\1[redacted]", str(message))
        return "OpenAI %s %s: %s" % (error.code, error_type, message[:350])

    @classmethod
    def _message_schema(cls):
        return {
            "name": "message_analysis",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string"},
                    "category": {"type": "string", "enum": ["customer", "supplier", "internal", "administrative", "technical", "sales", "support", "other", "customer_request", "finance", "project", "notification", "spam"]},
                    "importance": {"type": "string", "enum": cls._IMPORTANCE},
                    "requires_reply": {"type": "boolean"},
                    "requires_action": {"type": "boolean"},
                    "suggested_flow": {"type": ["string", "null"]},
                    "suggested_project": {"type": ["string", "null"]},
                    "suggested_owner": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "suggested_actions": {"type": "array", "items": cls._message_action_schema()},
                },
                "required": ["summary", "category", "importance", "requires_reply", "requires_action", "suggested_flow", "suggested_project", "suggested_owner", "confidence", "suggested_actions"],
            },
        }

    @classmethod
    def _meeting_schema(cls):
        return {
            "name": "meeting_analysis",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string"},
                    "importance": {"type": "string", "enum": cls._IMPORTANCE},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "decisions": {"type": "array", "items": cls._decision_schema()},
                    "suggested_actions": {"type": "array", "items": cls._meeting_action_schema()},
                    "open_questions": {"type": "array", "items": cls._question_schema()},
                },
                "required": ["summary", "importance", "confidence", "decisions", "suggested_actions", "open_questions"],
            },
        }

    @staticmethod
    def _decision_schema():
        return {
            "type": "object", "additionalProperties": False,
            "properties": {
                "title": {"type": "string"}, "description": {"type": ["string", "null"]},
                "responsible_user": {"type": ["string", "null"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["title", "description", "responsible_user", "confidence"],
        }

    @classmethod
    def _message_action_schema(cls):
        return {
            "type": "object", "additionalProperties": False,
            "properties": {
                "title": {"type": "string"}, "description": {"type": ["string", "null"]},
                "priority": {"type": "string", "enum": cls._PRIORITY},
                "due_date": {"type": ["string", "null"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": ["string", "null"]},
            },
            "required": ["title", "description", "priority", "due_date", "confidence", "reason"],
        }

    @classmethod
    def _meeting_action_schema(cls):
        return {
            "type": "object", "additionalProperties": False,
            "properties": {
                "title": {"type": "string"}, "priority": {"type": "string", "enum": cls._PRIORITY},
                "suggested_user": {"type": ["string", "null"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": ["string", "null"]},
            },
            "required": ["title", "priority", "suggested_user", "confidence", "reason"],
        }

    @classmethod
    def _question_schema(cls):
        return {
            "type": "object", "additionalProperties": False,
            "properties": {
                "question": {"type": "string"}, "owner": {"type": ["string", "null"]},
                "importance": {"type": "string", "enum": cls._IMPORTANCE}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["question", "owner", "importance", "confidence"],
        }
