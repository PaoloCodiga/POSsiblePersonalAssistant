class AiProvider:
    name = "base"

    def analyze_message(self, message):
        raise NotImplementedError

    def analyze_meeting(self, meeting):
        raise NotImplementedError
