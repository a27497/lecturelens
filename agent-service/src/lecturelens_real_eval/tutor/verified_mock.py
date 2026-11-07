"""Default Mock for the explicit v16 factory; no free-form assertion generation."""

import json

from .bounded_mock import SourcePreservingMock
from .citations import assembled_citation_ids


class VerifiedMock(SourcePreservingMock):
    def decide(self, messages, schemas, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["observations"]:
            return super().decide(messages, schemas, timeout)
        choices = [
            (e, p)
            for e in body["evidence"]
            for p in e["text"].split("\n\n")
            if p.strip() and len(p) <= 300 and not assembled_citation_ids(p)
        ]
        if not choices:
            args = {"outcome": "insufficient_evidence", "blocks": []}
        else:
            source, text = choices[0]
            if body["socratic"]:
                args = {
                    "outcome": "socratic_prompt",
                    "hint": {
                        "evidence_id": source["evidence_id"],
                        "quote": text[:240],
                        "intent": "locate_rule",
                    },
                }
            else:
                args = {
                    "outcome": "answered",
                    "blocks": [{"kind": "source", "text": text, "evidence_id": source["evidence_id"]}],
                }
                if body["evaluation_required"]:
                    args["evaluation_blocks"] = [
                        {
                            "evidence_id": source["evidence_id"],
                            "learner_quote": body["learner_text"][:40],
                            "quote": text[:90],
                        }
                    ]
        return {
            "name": "finish_tutor_turn",
            "arguments": args,
            "usage": {"prompt_tokens": 100, "completion_tokens": 60},
        }
