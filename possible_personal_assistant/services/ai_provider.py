class AiProvider:
    name = "base"

    def analyze_message(self, message):
        raise NotImplementedError
