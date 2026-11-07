"""Deterministic source selection for opt-in v19; never a semantic quality model."""

import json

from .citations import assembled_citation_ids


class SelectedMock:
    def decide(self, messages, schemas, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["observations"]:
            return dict(
                name="search_tutor_evidence",
                arguments=dict(query=body["learner_text"][:500]),
                usage=dict(prompt_tokens=100, completion_tokens=20),
            )
        choices = [
            (e, n, t)
            for e in body["evidence"]
            for n, t in e["source_units"]
            if t.strip() and not assembled_citation_ids(t)
        ]
        if not choices:
            result = dict(outcome="insufficient_evidence")
        else:
            e, n, text = choices[0]
            span = dict(evidence_id=e["evidence_id"], first_unit=n, last_unit=n)
            if body["socratic"]:
                result = dict(outcome="socratic_prompt", hint=dict(span=span, intent="locate_rule"))
            else:
                full = "".join(t for _, t in e["source_units"])
                if len(full) <= 900 and not assembled_citation_ids(full):
                    answer_span = span | dict(first_unit=1, last_unit=len(e["source_units"]))
                else:
                    answer_span = span
                result = dict(outcome="answered", blocks=[dict(kind="source", span=answer_span)])
                if body["evaluation_required"]:
                    result["evaluation_blocks"] = [
                        dict(
                            span=span,
                            learner_quote=body["learner_text"][:200],
                            text="Compare your reply with this source: " + text,
                        )
                    ]
        return dict(
            name="finish_tutor_turn", arguments=result, usage=dict(prompt_tokens=100, completion_tokens=60)
        )
