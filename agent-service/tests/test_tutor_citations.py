import json
from pathlib import Path

import pytest

from lecturelens_real_eval.tutor.citations import EVIDENCE_ID, inline_citation_ids
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


@pytest.mark.parametrize("text", ["Adj[u]", "A[i]", "[0, n)", "[0, n]", "[u]", "[fake-id]"])
def test_non_id_brackets_are_ordinary_text(text):
    assert inline_citation_ids(text) == []


@pytest.mark.parametrize("declared", ["v2-algorithms-l1-p99-e00", None, 42, {"id": "unknown"}])
def test_malformed_declarations_remain_visible_to_authority_check(declared):
    assert citation_ids({"text": "Adj[u]", "evidence_ids": declared}) == [declared]


def test_finish_model_schema_retains_all_publication_limits():
    from lecturelens_real_eval.tutor.contracts import Finish
    from lecturelens_real_eval.tutor.runtime import SYSTEM

    properties = Finish.model_json_schema()["properties"]
    assert properties["evidence_ids"]["maxItems"] == 4
    assert properties["evaluation"]["maxLength"] == 500
    assert properties["text"]["maxLength"] == 1600
    assert all(s in SYSTEM for s in ("4 unique ids", "500 characters", "1600 characters"))


@pytest.mark.parametrize(
    "change",
    [
        {"outcome": "bad"},
        {"text": ""},
        {"evaluation": 524},
        {"evidence_ids": ["e1"] * 4 + [42]},
        {"evidence_ids": ["e1"] * 4 + ["x" * 129]},
        {"evidence_ids": ("e1",)},
        {"extra": True},
    ],
)
def test_relaxed_proposal_preserves_every_non_limit_schema_constraint(change):
    from pydantic import ValidationError

    from lecturelens_real_eval.tutor.contracts import validate_proposal

    args = dict(outcome="answered", text="T" * 1601, evaluation="E" * 501, evidence_ids=["e1"] * 8)
    with pytest.raises(ValidationError):
        validate_proposal("finish_tutor_turn", {**args, **change})
