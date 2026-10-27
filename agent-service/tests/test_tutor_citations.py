import json
from pathlib import Path

import pytest

from lecturelens_real_eval.tutor.citations import EVIDENCE_ID, assembled_citation_ids, inline_citation_ids
from lecturelens_real_eval.tutor_runner import citation_ids


def test_grammar_covers_every_source_corpus_and_snapshot_id():
    root = Path(__file__).resolve().parents[2]
    corpus = json.loads((root / "eval/retrieval-v2/corpus.json").read_text())
    snapshot = json.loads((root / "eval/p7-real/snapshot.json").read_text())
    for source in (corpus["courses"], snapshot["lectures"]):
        for course in source.values():
            assert all(EVIDENCE_ID.fullmatch(e["evidence_id"]) for e in course["evidence"])


@pytest.mark.parametrize(
    "evidence_id",
    ["0123456789abcdef" * 4, "e1", "e123", "v2-algorithms-l1-p03-e00", "v2-algorithms-l1-p04-e00-zh"],
)
def test_production_hash_short_alias_and_snapshot_candidates(evidence_id):
    assert inline_citation_ids(f"Claim [{evidence_id}]") == [evidence_id]


@pytest.mark.parametrize(
    "text", ["Adj[u]", "A[i]", "[0, n)", "[0, n]", "[u]", "[v]", "[A]", "[x_1]", "[fake-id]"]
)
def test_non_id_brackets_are_ordinary_text(text):
    assert inline_citation_ids(text) == []
    assert assembled_citation_ids(f"{text} [e2]", f"{text} [e1]") == ["e2", "e1"]


@pytest.mark.parametrize("declared", ["v2-algorithms-l1-p99-e00", None, 42, {"id": "unknown"}])
def test_declarations_are_ignored_by_authority_check(declared):
    assert citation_ids({"text": "Adj[u]", "evidence_ids": declared}) == []


def test_finish_model_schema_retains_all_publication_limits():
    from lecturelens_real_eval.tutor.contracts import Finish
    from lecturelens_real_eval.tutor.runtime import FINISH_LIMITS, SYSTEM

    properties = Finish.model_json_schema()["properties"]
    assert properties["evidence_ids"]["maxItems"] == 4
    assert properties["evaluation"]["maxLength"] == 500
    assert properties["text"]["maxLength"] == 1600
    assert all(s in SYSTEM for s in ("4 distinct evidence ids", "500 characters", "1600 characters"))
    assert FINISH_LIMITS in SYSTEM
    assert all(s in FINISH_LIMITS for s in ("prefer 2–3", "≤1200", "Only cite ids from observations", "math"))


@pytest.mark.parametrize(
    "change",
    [
        {"outcome": "bad"},
        {"text": ""},
        {"evaluation": 524},
        {"extra": True},
    ],
)
def test_relaxed_proposal_preserves_every_non_limit_schema_constraint(change):
    from pydantic import ValidationError

    from lecturelens_real_eval.tutor.contracts import validate_proposal

    args = dict(outcome="answered", text="T" * 1601, evaluation="E" * 501, evidence_ids=["e1"] * 8)
    with pytest.raises(ValidationError):
        validate_proposal("finish_tutor_turn", {**args, **change})


def test_model_tool_omits_declaration_and_controller_extraction_is_ordered():
    from lecturelens_real_eval.tutor.citations import assembled_citation_ids
    from lecturelens_real_eval.tutor.contracts import TOOLS, validate_proposal

    properties = TOOLS["finish_tutor_turn"].model_json_schema()["properties"]
    assert "evidence_ids" not in properties
    assert properties["text"]["maxLength"] == 1600
    assert properties["evaluation"]["maxLength"] == 500
    assert assembled_citation_ids("[e3] [e1] [e3]", "[e2] [e1] [e99]") == ["e3", "e1", "e2", "e99"]
    args = dict(outcome="answered", text="[e1]", evidence_ids={"arbitrary": "ignored"})
    assert "evidence_ids" not in validate_proposal("finish_tutor_turn", args).model_dump()
