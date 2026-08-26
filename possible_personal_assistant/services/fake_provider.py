from .ai_provider import AiProvider


class FakeProvider(AiProvider):
    name = "fake"

    def analyze_message(self, message):
        text = "%s %s" % (message.subject or "", message.body or "")
        if "provider failure" in text.lower():
            raise RuntimeError("Fake provider failure")
        if "closed" in text.lower():
            return {"summary": "Informational notification.", "category": "notification", "importance": "normal", "requires_reply": False, "requires_action": False, "confidence": 0.9, "suggested_actions": []}
        actions = [{"title": "Verify updated prices", "description": "Verify the prices requested in the message.", "priority": "important", "confidence": 0.9, "reason": "The message requests price verification."}]
        if "multiple actions" in text.lower():
            actions = actions * 3
        return {"summary": "Customer requests confirmation of updated prices.", "category": "customer_request", "importance": "important", "requires_reply": True, "requires_action": True, "confidence": 0.94, "suggested_actions": actions}

    def analyze_meeting(self, meeting):
        text = "%s %s" % (meeting.name or "", meeting.transcript or "")
        if "meeting_failure" in text:
            raise RuntimeError("Fake meeting provider failure")
        if "meeting_no_actions" in text:
            return {"summary": "General company update.", "importance": "normal", "confidence": 0.9, "decisions": [], "suggested_actions": [], "open_questions": []}
        if "meeting_invalid" in text:
            return {"summary": "Invalid", "importance": "unknown", "confidence": 2, "decisions": [], "suggested_actions": [], "open_questions": []}
        if "meeting_decisions_only" in text:
            return {"summary": "Decision meeting.", "importance": "important", "confidence": 0.9, "decisions": [{"title": "Approve plan", "confidence": 0.9}], "suggested_actions": [], "open_questions": []}
        if "meeting_actions_only" in text:
            return {"summary": "Action meeting.", "importance": "important", "confidence": 0.9, "decisions": [], "suggested_actions": [{"title": "Prepare package", "priority": "important", "confidence": 0.9}], "open_questions": []}
        decisions = [{"title": "Approve deployment plan", "description": "The deployment plan was approved.", "confidence": 0.9, "reason": "Explicitly approved."}, {"title": "Select certification path", "description": "Certification path was agreed.", "confidence": 0.88, "reason": "Explicit agreement."}]
        actions = [{"title": "Prepare deployment", "priority": "important", "confidence": 0.9, "reason": "Assigned follow-up."}] * 3
        questions = [{"question": "Who confirms certification timing?", "importance": "important", "confidence": 0.8}, {"question": "Which deployment window is preferred?", "importance": "normal", "confidence": 0.8}]
        return {"summary": "Development meeting covering certification and deployment.", "importance": "important", "confidence": 0.93, "decisions": decisions, "suggested_actions": actions, "open_questions": questions}
