import json
import os
from urllib import request as urlrequest

from .ai_provider import AiProvider
from .prompts import MESSAGE_ANALYSIS_SYSTEM_PROMPT


class OpenAiProvider(AiProvider):
    name = "openai"

    def analyze_message(self, message):
        api_key = os.getenv("PPA_OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OpenAI API key is not configured.")
        model = os.getenv("PPA_OPENAI_MODEL", "gpt-4.1-mini")
        payload = {"model": model, "input": [{"role": "system", "content": MESSAGE_ANALYSIS_SYSTEM_PROMPT}, {"role": "user", "content": "Subject: %s\nBody: %s" % (message.subject or "", message.body or "")}], "text": {"format": {"type": "json_object"}}}
        request = urlrequest.Request("https://api.openai.com/v1/responses", data=json.dumps(payload).encode(), headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"}, method="POST")
        timeout = int(os.getenv("PPA_AI_TIMEOUT_SECONDS", "60"))
        with urlrequest.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode())
        return json.loads(result["output"][0]["content"][0]["text"])
