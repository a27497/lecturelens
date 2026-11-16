import hashlib

import pytest
from pydantic import ValidationError

from lecturelens_agent.study.decision import prepare_tool_call
from lecturelens_agent.study.errors import StudyError


def test_selected_alias_produces_canonical_checkpoint_payload():
    raw = {"evidence_id": "e1"}
    aliases = {"e1": "course-passage-7"}
    call = prepare_tool_call("read_evidence_window", raw, goal="explain", history=[], aliases=aliases)

    assert call == {
        "name": "read_evidence_window",
        "arguments": {"evidence_id": "course-passage-7"},
        "fingerprint": hashlib.sha256(
            b'["read_evidence_window", {"evidence_id": "course-passage-7"}]'
        ).hexdigest(),
        "evidence_aliases": aliases,
    }
    assert raw == {"evidence_id": "e1"}
    with pytest.raises(StudyError, match="UNSUPPORTED_CITATION"):
        prepare_tool_call("read_evidence_window", raw, goal="explain", history=[], aliases={})


def test_search_validates_unsolicited_window_before_removing_it():
    raw = {"query": "stopping condition", "start_ms": 90_000, "end_ms": 120_000}
    call = prepare_tool_call("search_course_evidence", raw, goal="explain", history=[], aliases={})
    assert not {"start_ms", "end_ms"} & call["arguments"].keys()
    timed = prepare_tool_call("search_course_evidence", raw, goal="explain at 01:30", history=[], aliases={})
    assert timed["arguments"]["start_ms"] == 90_000
    assert timed["arguments"]["end_ms"] == 120_000
    with pytest.raises(ValidationError):
        prepare_tool_call(
            "search_course_evidence", {**raw, "end_ms": 2}, goal="explain", history=[], aliases={}
        )


def test_abstention_requires_a_completed_search_in_history():
    raw = {"reason": "No source teaches that concept."}
    with pytest.raises(StudyError, match="SEARCH_REQUIRED"):
        prepare_tool_call("report_insufficient_evidence", raw, goal="explain", history=[], aliases={})
    call = prepare_tool_call(
        "report_insufficient_evidence",
        raw,
        goal="explain",
        history=[{"tool": "search_course_evidence", "result": {}}],
        aliases={},
    )
    assert call["arguments"] == raw
