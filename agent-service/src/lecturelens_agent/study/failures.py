"""Public, payload-free failure labels for execution symptoms."""


def failure_category(code):
    if code == "APPROVAL_REJECTED":
        return "human_approval"
    if code in {
        "READ_CHECKPOINT_REPLAY",
        "MODEL_OUTCOME_UNKNOWN",
        "MODEL_INPUT_CHANGED",
        "MODEL_JOURNAL_VERSION_CHANGED",
    }:
        return "checkpoint_recovery"
    if code in {"UNKNOWN_TOOL", "SEARCH_REQUIRED", "ARTIFACT_MUST_END_RUN", "REPEATED_TOOL_WITHOUT_PROGRESS"}:
        return "model_tool_selection"
    if code in {"INVALID_TOOL_ARGUMENTS", "MCP_INVALID_REQUEST"}:
        return "invalid_parameters"
    if code in {
        "MODEL_TOOL_CONTRACT",
        "MODEL_OUTPUT_TRUNCATED",
        "MODEL_FEEDBACK_CONTRACT",
        "MODEL_REVIEW_CONTRACT",
    }:
        return "model_protocol"
    if "MALFORMED" in code or code == "MCP_CONTRACT_MISMATCH":
        return "malformed_response"
    if any(part in code for part in ("SCOPE", "CHANGED", "STALE", "CANCEL")):
        return "permission_state"
    if "TIMEOUT" in code:
        return "timeout"
    if "BUDGET" in code or "DEADLINE" in code:
        return "budget"
    return "tool_dependency_unavailable"
