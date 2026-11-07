"""Default provider of the explicit v15 factory; no provider client or credentials."""

import json

from .citations import assembled_citation_ids


class SourcePreservingMock:
    mode = "mock"

    def decide(self, messages, schemas, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["observations"]:
            previous = body["history"][-1]["learner_text"] if body["history"] else ""
            return {
                "name": "search_tutor_evidence",
                "arguments": {"query": (body["learner_text"] + " " + previous)[-500:]},
            }
        chosen = None
        for source in body["evidence"]:
            for paragraph in source["text"].split("\n\n"):
                if paragraph.strip() and len(paragraph) <= 300 and not assembled_citation_ids(paragraph):
                    chosen = source, paragraph
                    break
            if chosen:
                break
        if not chosen:
            args = dict(outcome="insufficient_evidence", blocks=[])
        else:
            source, paragraph = chosen
            block = dict(
                text=paragraph, evidence_id=source["evidence_id"], quote=paragraph[:240], basis="course"
            )
            if body["socratic"]:
                block["text"] = "Which condition in this source helps you choose your next step?"
            args = dict(outcome="socratic_prompt" if body["socratic"] else "answered", blocks=[block])
            if body["evaluation_required"]:
                args["evaluation_blocks"] = [
                    {
                        **block,
                        "text": "Compare your reply with this cited course statement. This is guidance, not an automatic grade.",
                    }
                ]
        return {
            "name": "finish_tutor_turn",
            "arguments": args,
            "usage": {"prompt_tokens": 100, "completion_tokens": 60},
        }
