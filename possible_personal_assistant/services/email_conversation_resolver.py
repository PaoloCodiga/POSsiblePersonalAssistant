from .ingestion.email_normalizer import EmailNormalizer


class EmailConversationResolver:
    """Resolve only explicit or demonstrably safe email threading links."""

    def __init__(self, env, source):
        self.env, self.source = env, source

    def resolve(self, email):
        Message = self.env["ppa.message"]
        identifiers = [email.get("in_reply_to")] + email.get("references", [])
        for identifier in filter(None, identifiers):
            message = Message.search([
                ("source_id", "=", self.source.id), ("email_message_id", "=", identifier),
                ("mailbox_id", "=", email.get("mailbox_id") or False),
            ], limit=1)
            if message and message.conversation_id:
                return message.conversation_id
        thread_id = email.get("provider_thread_id")
        if thread_id:
            conversation = self.env["ppa.conversation"].search([
                ("source_id", "=", self.source.id), ("external_id", "=", "email-thread:%s" % thread_id),
                ("mailbox_id", "=", email.get("mailbox_id") or False),
            ], limit=1)
            if conversation:
                return conversation
        return self._safe_subject_match(email)

    def _safe_subject_match(self, email):
        subject = EmailNormalizer.normalize_subject(email.get("subject"))
        senders = {item["address"] for item in email.get("from", [])}
        if not subject or not senders:
            return self.env["ppa.conversation"]
        candidates = self.env["ppa.message"].search([
            ("source_id", "=", self.source.id), ("subject", "!=", False),
            ("mailbox_id", "=", email.get("mailbox_id") or False),
        ]).filtered(lambda message: (
            EmailNormalizer.normalize_subject(message.subject) == subject
            and senders.intersection(self._addresses(message.email_from))
            and message.conversation_id
        )).mapped("conversation_id")
        return candidates if len(candidates) == 1 else self.env["ppa.conversation"]

    @staticmethod
    def _addresses(value):
        import json
        try:
            return {item.get("address") for item in json.loads(value or "[]") if item.get("address")}
        except (TypeError, ValueError):
            return set()
