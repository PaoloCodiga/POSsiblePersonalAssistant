MESSAGE_ANALYSIS_PROMPT_VERSION = "message-analysis-v1"
MEETING_ANALYSIS_PROMPT_VERSION = "meeting-analysis-v1"
MEETING_ANALYSIS_SYSTEM_PROMPT = """Analyze only the supplied meeting. Return structured data: accurate summary, importance, confidence, actual decisions only, explicit actions only, and unresolved questions. Never invent owners, deadlines, or decisions."""
MESSAGE_ANALYSIS_SYSTEM_PROMPT = """Analyze only the supplied message. Return JSON with summary, category, importance, requires_reply, requires_action, confidence, and suggested_actions. Do not invent owners, deadlines, or tasks. Use absolute ISO dates only when explicitly clear."""
