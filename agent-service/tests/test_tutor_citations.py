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
