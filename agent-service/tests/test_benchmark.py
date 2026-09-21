import copy
import json
import math
import os
import uuid
from pathlib import Path

import pytest

from lecturelens_agent.benchmark.answers import parse_answer
from lecturelens_agent.benchmark.core import (
    BM25,
    STRATEGIES,
    Ablations,
    digest,
    fuse,
    percentile,
    retrieval_metrics,
    validate_dataset,
    verify_freeze,
)
from lecturelens_agent.benchmark.report import answer_metrics
from lecturelens_agent.contracts import SyncRequest
from lecturelens_agent.retrieval import IndexNotReady
from lecturelens_agent.store import VectorStore

DATA = Path(__file__).resolve().parents[2] / "eval/retrieval-phase-a"


def test_real_snapshot_gold_integrity_and_reject_foreign_or_contradictory_gold():
    corpus = json.loads((DATA / "corpus.json").read_text())
    cases = json.loads((DATA / "cases.json").read_text())
    validate_dataset(corpus, cases)
    bad = copy.deepcopy(cases)
    bad["cases"][0]["aspects"][0]["evidence_ids"].append("foreign")
    with pytest.raises(ValueError, match="outside course"):
        validate_dataset(corpus, bad)
    bad = copy.deepcopy(cases)
    bad["cases"][0]["hard_negative_ids"] = bad["cases"][0]["aspects"][0]["evidence_ids"][:1]
    with pytest.raises(ValueError, match="also hard negative"):
        validate_dataset(corpus, bad)


def test_hand_calculated_metrics_and_aspect_alternatives():
    case = {
        "answerable": True,
        "aspects": [{"evidence_ids": ["a", "a-translation"]}, {"evidence_ids": ["b"]}],
    }
    m = retrieval_metrics(["noise", "b", "a"], case, 3)
    assert m["recall"] == 2 / 3
    assert m["mrr"] == 0.5
    assert m["evidence_coverage"] == 1
    assert m["ndcg"] == pytest.approx((1 / math.log2(3) + 0.5) / (1 + 1 / math.log2(3) + 0.5))
    assert retrieval_metrics([], case, 3)["recall"] == 0
    assert retrieval_metrics(["noise"], {"answerable": False}, 3) is None
    with pytest.raises(ValueError, match="Duplicate"):
        retrieval_metrics(["a", "a"], case, 3)


def test_rrf_is_score_scale_independent_and_weighted_fusion_is_distinct():
    dense, sparse = [("a", 0.9), ("b", 0.1)], [("b", 10), ("a", 1)]
    rrf = fuse(dense, sparse, "rrf")
    assert rrf == fuse([(k, v * 100) for k, v in dense], sparse, "rrf")
    assert rrf[0][0] == "a"  # tie broken by Evidence ID, not arrival order
    assert fuse(dense, sparse, "score")[0][0] == "b"


def test_bm25_has_cjk_support_and_respects_eligible_set():
    bm = BM25({"a": "字符串 immutable", "b": "matrix"})
    assert bm.search("字符串", {"a", "b"}, 8)[0][0] == "a"
    assert bm.search("immutable", {"b"}, 8) == []
    assert bm.search("unseen", {"a", "b"}, 8) == []


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        '{"answer":"x","refused":false,"citations":[]}',
        '{"answer":"x","refused":false,"citations":["FOREIGN"]}',
        '{"answer":"x","refused":"false","citations":["E1"]}',
        '{"answer":"x","refused":false,"citations":["E1","E1"]}',
    ],
)
def test_reader_rejects_invalid_protocol_and_citations(text):
    with pytest.raises(ValueError):
        parse_answer(text, ["E1"])


def test_refusal_accuracy_is_not_answer_correctness_and_errors_remain_failures():
    rows, reviews = [], []
    for strategy in STRATEGIES:
        for cid in ("yes", "no"):
            rows.append(
                {
                    "case_id": cid,
                    "strategy": strategy,
                    "response_sha256": "hash",
                    "answer": {"answer": "wrong", "refused": False, "citations": ["a"]},
                }
            )
            reviews.append(
                {
                    "case_id": cid,
                    "strategy": strategy,
                    "response_sha256": "hash",
                    "answer_correct": False,
                    "all_claims_supported": False,
                    "all_required_aspects": False,
                    "reason": "unsupported statement",
                }
            )
    cases = {"yes": {"answerable": True}, "no": {"answerable": False}}
    summary, _ = answer_metrics(rows, cases, reviews)
    assert summary["dense"]["grounded_answer_rate"] == 0
    assert summary["dense"]["refusal_accuracy"] == 0.5
    assert summary["dense"]["no_answer_refusal_rate"] == 0
    rows[0]["error_type"] = "TimeoutException"
    summary, _ = answer_metrics(rows, cases, reviews)
    assert summary["dense"]["protocol_errors"] == 1
    assert summary["dense"]["refusal_accuracy"] == 0
    reviews[0]["response_sha256"] = "different"
    with pytest.raises(ValueError, match="another response"):
        answer_metrics(rows, cases, reviews)


def test_frozen_candidate_changes_are_rejected(tmp_path):
    dataset = tmp_path / "eval/bench"
    dataset.mkdir(parents=True)
    code = tmp_path / "code.py"
    code.write_text("original")
    (dataset / "freeze.json").write_text(json.dumps({"files": {"code.py": digest(code)}}))
    verify_freeze(dataset)
    code.write_text("changed")
    with pytest.raises(ValueError, match="Frozen input/code changed"):
        verify_freeze(dataset)


def test_latency_percentile_definition():
    assert percentile([10, 20, 30, 40], 0.95) == pytest.approx(38.5)
    with pytest.raises(ValueError):
        percentile([], 0.95)


class TinyEmbedding:
    index_version = "benchmark-test-only"
    dimensions = 2

    def embed(self, texts):
        return [[1.0, 0.1] if "bread" in t else [0.1, 1.0] for t in texts]


class TinyReranker:
    def rerank(self, query, documents, batch_size=32):
        return [2.0 if query in text else 0.0 for text in documents]


@pytest.fixture
def ablations():
    dsn = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Requires separate PostgreSQL test DB")
    store = VectorStore(dsn)
    store.initialize()
    engine = Ablations(
        store,
        TinyEmbedding(),
        TinyReranker(),
        {
            "bm25": {"k1": 1.2, "b": 0.75},
            "candidate_k": 8,
            "rerank_k": 8,
            "rrf_k": 60,
            "dense_weight": 0.5,
        },
    )
    scope = {"owner_id": 87651, "course_id": "benchmark-test-" + uuid.uuid4().hex, "revision": 1}
    engine.prepare(
        "test",
        {
            "scope": scope,
            "evidence": [
                {
                    "evidence_id": "a",
                    "text": "bread recipe",
                    "start_ms": 0,
                    "end_ms": 999,
                    "retrievable": True,
                },
                {
                    "evidence_id": "b",
                    "text": "matrix multiplication",
                    "start_ms": 1000,
                    "end_ms": 1999,
                    "retrievable": True,
                },
            ],
        },
    )
    yield engine, scope
    engine.retriever.sync(SyncRequest(request_id="cleanup", **scope, sequence=99, operation="DELETE"))


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_all_ablations_preserve_owner_revision_allowlist_window_and_deletion(ablations, strategy):
    engine, scope = ablations
    assert engine.search("test", "bread", strategy)[0][0] == "a"
    assert [key for key, _ in engine.search("test", "bread", strategy, allowed_ids=["b"])] == ["b"]
    assert [
        key
        for key, _ in engine.search("test", "bread", strategy, time_window={"start_ms": 1000, "end_ms": 1100})
    ] == ["b"]
    for wrong in ({"owner_id": 87652}, {"revision": 2}, {"course_id": "other"}):
        with pytest.raises(IndexNotReady):
            engine.search("test", "bread", strategy, scope=scope | wrong)
    engine.retriever.sync(SyncRequest(request_id="delete", **scope, sequence=2, operation="DELETE"))
    with pytest.raises(IndexNotReady):
        engine.search("test", "bread", strategy)


def test_delete_during_rerank_cannot_return_cached_hits(ablations):
    engine, scope = ablations

    def delete(query, documents, batch_size=32):
        engine.retriever.sync(SyncRequest(request_id="delete", **scope, sequence=2, operation="DELETE"))
        return [1.0] * len(documents)

    engine.cross_encoder.rerank = delete
    with pytest.raises(ValueError, match="Snapshot changed"):
        engine.search("test", "bread", "hybrid_rrf_ce")
