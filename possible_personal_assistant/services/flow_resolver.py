class FlowResolver:
    """Safe deterministic Flow matching; this service never creates Flows."""

    def __init__(self, env):
        self.env = env

    def resolve(self, conversation, external_reference=None, source=None, message_ids=None):
        if conversation and conversation.flow_id:
            return conversation.flow_id
        if source and message_ids:
            messages = self.env["ppa.message"].search([
                ("source_id", "=", source.id), ("email_message_id", "in", message_ids), ("flow_id", "!=", False),
            ])
            if len(messages.mapped("flow_id")) == 1:
                return messages.mapped("flow_id")
        if external_reference:
            flows = self.env["ppa.flow"].search([("external_reference", "=", external_reference)])
            if len(flows) == 1:
                return flows
        return self.env["ppa.flow"]
