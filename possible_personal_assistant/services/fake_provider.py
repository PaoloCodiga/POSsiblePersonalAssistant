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
