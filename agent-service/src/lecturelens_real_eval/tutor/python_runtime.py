"""Explicit development prompt variant; the frozen v9 runtime remains reproducible."""

import json

from .runtime import FINISH_LIMITS as V9_FINISH_LIMITS
from .runtime import SYSTEM as V9_SYSTEM
from .runtime import TutorRuntime as V9TutorRuntime

CODE_NOTATION = (
    "Preserve valid programming syntax, including array indexing and slicing with square brackets "
    "such as data[29, 19], data[0:4, 0:10], data[:3, 36:] and A[:, :1]. "
    "This applies to inline code and fenced code blocks. Never rewrite indexing as a function call. "
    "Place course citations as [evidence_id] next to the supported claim, preferably outside code. "
    "Ordinary non-ID-shaped brackets are not citations. A bracket token matching the evidence-ID grammar "
    "remains a citation candidate even inside code; code formatting never bypasses observed-ID or authority "
    "checks. Use descriptive index variable names rather than reserved evidence-ID-shaped names such as e1."
)


def _replace_once(text, before, after):
    # A changed parent requires a new reviewed variant, not a silent partial substitution.
    if text.count(before) != 1:
        raise ValueError("TUTOR_PYTHON_PARENT_PROMPT_CHANGED")
    return text.replace(before, after, 1)


FINISH_LIMITS = _replace_once(
    V9_FINISH_LIMITS,
    "Do not write math symbols or variables in square brackets; use parentheses instead.",
    CODE_NOTATION,
)
SYSTEM = _replace_once(V9_SYSTEM, V9_FINISH_LIMITS, FINISH_LIMITS)
SYSTEM = _replace_once(
    SYSTEM,
    "Reserve square brackets for citations; use parentheses for math/indexing.",
    "Preserve language-defined brackets in code; course citations still use only [evidence_id].",
)


class PythonTutorRuntime(V9TutorRuntime):
    """Select explicitly with the v10 development manifest; no default/product switch."""

    def request(self, session, turn, state, history):
        messages, schemas, _ = super().request(session, turn, state, history)
        messages[0] = {"role": "system", "content": SYSTEM}
        for schema in schemas:
            if schema["function"]["name"] == "finish_tutor_turn":
                schema["function"]["description"] = FINISH_LIMITS
        # The changed prompt/schema bytes must be reserved on first dispatch AND prepaid repairs.
        amount = len(json.dumps([messages, schemas], ensure_ascii=False).encode()) + 1200
        return messages, schemas, amount
