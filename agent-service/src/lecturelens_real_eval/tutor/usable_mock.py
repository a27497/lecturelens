"""Source-preserving Mock verifies protocol mechanics, never teaching quality."""

from .verified_mock import VerifiedMock


class UsableMock(VerifiedMock):
    def decide(self, messages, schemas, timeout):
        result = super().decide(messages, schemas, timeout)
        if result["name"] == "finish_tutor_turn":
            for value in result["arguments"].get("evaluation_blocks", []):
                value["text"] = "Compare your reply with this source: " + value["quote"]
        return result
