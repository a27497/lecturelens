"""Bounded, deterministic retrieval ablations and explicitly defined metrics."""

import hashlib
import json
import math
import re
from collections import Counter
from importlib.metadata import version
from pathlib import Path

from lecturelens_agent.contracts import Evidence, EvidenceMetadata, RetrieveRequest, SyncRequest
from lecturelens_agent.retrieval import Retriever, split_evidence

STRATEGIES = ("dense", "bm25_dense", "hybrid_rrf", "hybrid_rrf_ce")
CATEGORIES = {
    "lexical",
    "semantic",
    "multi-condition",
    "cross-section",
    "exception-no-answer",
    "confusing-evidence-hard-negative",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tokens(text):
    # No external tokenizer, stemming, translation, or evaluation-driven synonym expansion.
    return re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", text.lower())


class BM25:
    def __init__(self, documents, k1=1.2, b=0.75):
        self.docs = {key: Counter(tokens(value)) for key, value in documents.items()}
        self.lengths = {key: sum(value.values()) for key, value in self.docs.items()}
        self.avg = sum(self.lengths.values()) / max(1, len(self.docs))
        self.df = Counter(term for doc in self.docs.values() for term in doc)
        self.k1, self.b = k1, b

    def search(self, query, allowed, limit):
        scores = {}
        for key in sorted(allowed):
            doc = self.docs[key]
            score = 0.0
            for term in set(tokens(query)):
                freq = doc[term]
                if freq:
                    idf = math.log(1 + (len(self.docs) - self.df[term] + 0.5) / (self.df[term] + 0.5))
                    score += (
                        idf
                        * freq
                        * (self.k1 + 1)
                        / (freq + self.k1 * (1 - self.b + self.b * self.lengths[key] / self.avg))
                    )
            if score > 0:
                scores[key] = score
        return ranked(scores)[:limit]


def ranked(scores):
    if not all(math.isfinite(v) for v in scores.values()):
        raise ValueError("Nonfinite score")
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def fuse(dense, sparse, method, rrf_k=60, alpha=0.5):
    scores = {}
    for weight, branch in ((alpha, dense), (1 - alpha, sparse)):
        maximum = max((max(0, value) for _, value in branch), default=0)
        for rank, (key, value) in enumerate(branch, 1):
            # Missing candidates contribute zero. RRF gives equal weight to each branch.
            contribution = (
                1 / (rrf_k + rank)
                if method == "rrf"
                else (weight * max(0, value) / maximum if maximum else 0)
            )
            scores[key] = scores.get(key, 0) + contribution
    return ranked(scores)


def eligible(evidence, request):
    allowed = set(request.allowed_evidence_ids)
    window = request.time_window
    return {
        e.evidence_id
        for e in evidence
        if e.evidence_id in allowed
        and (window is None or e.start_ms <= window.end_ms and e.end_ms >= window.start_ms)
    }


class Ablations:
    def __init__(self, store, embedder, cross_encoder, config):
        self.retriever = Retriever(store, embedder)
        self.cross_encoder, self.config = cross_encoder, config
        self.courses = {}

    def prepare(self, name, course):
        evidence = [
            Evidence(**{k: e[k] for k in ("evidence_id", "text", "start_ms", "end_ms")})
            for e in course["evidence"]
            if e["retrievable"]
        ]
        self.retriever.sync(
            SyncRequest(
                request_id="phase-a-index",
                **course["scope"],
                sequence=1,
                operation="APPLY",
                manifest=[
                    EvidenceMetadata(
                        evidence_id=e.evidence_id,
                        content_hash=hashlib.sha256(e.text.encode()).hexdigest(),
                        start_ms=e.start_ms,
                        end_ms=e.end_ms,
                    )
                    for e in evidence
                ],
                upserts=evidence,
                index_version=self.retriever.embedder.index_version,
            )
        )
        sparse = BM25({e.evidence_id: e.text for e in evidence}, **self.config["bm25"])
        self.courses[name] = (course["scope"], evidence, sparse)

    def search(self, name, query, strategy, *, allowed_ids=None, time_window=None, scope=None):
        if strategy not in STRATEGIES:
            raise ValueError("Unknown strategy")
        original_scope, evidence, sparse = self.courses[name]
        req = RetrieveRequest(
            request_id="phase-a-query",
            **(scope or original_scope),
            query=query,
            top_k=self.config["candidate_k"],
            time_window=time_window,
            allowed_evidence_ids=allowed_ids
            if allowed_ids is not None
            else [e.evidence_id for e in evidence],
        )
        # Reuse production version/owner/deletion/allowlist checks before every branch.
        response = self.retriever.search(req)
        dense = [(hit.evidence_id, hit.score) for hit in response.hits]
        if strategy == "dense":
            return dense
        allowed = eligible(evidence, req)
        lexical = sparse.search(query, allowed, self.config["candidate_k"])
        result = fuse(
            dense,
            lexical,
            "score" if strategy == "bm25_dense" else "rrf",
            self.config["rrf_k"],
            self.config["dense_weight"],
        )
        if strategy == "hybrid_rrf_ce":
            candidates = {key for key, _ in result[: self.config["rerank_k"]]}
            chunks = [
                (e.evidence_id, text) for e, text in split_evidence(evidence) if e.evidence_id in candidates
            ]
            values = list(self.cross_encoder.rerank(query, [text for _, text in chunks], batch_size=32))
            if len(values) != len(chunks):
                raise ValueError("Reranker result count mismatch")
            scores = {}
            for (key, _), value in zip(chunks, values, strict=True):
                if not math.isfinite(value):
                    raise ValueError("Nonfinite reranker score")
                scores[key] = max(scores.get(key, -math.inf), float(value))
            result = ranked(scores)
        # Recheck readiness after CPU work. This is an offline snapshot, not a live Java gateway.
        if (
            self.retriever.store.ready_snapshot(req, self.retriever.embedder.index_version)
            != response.snapshot_id
        ):
            raise ValueError("Snapshot changed during benchmark query")
        return result[: self.config["candidate_k"]]


def retrieval_metrics(ids, case, k):
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate retrieved Evidence IDs")
    if not case["answerable"]:
        return None  # No relevance denominator; never manufacture perfect recall on no-answer.
    gold = {eid for aspect in case["aspects"] for eid in aspect["evidence_ids"]}
    top = ids[:k]
    relevance = [int(eid in gold) for eid in top]
    dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(relevance))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(gold))))
    return {
        "recall": len(set(top) & gold) / len(gold),
        "mrr": next((1 / (i + 1) for i, rel in enumerate(relevance) if rel), 0),
        "ndcg": dcg / ideal,
        "evidence_coverage": sum(bool(set(a["evidence_ids"]) & set(top)) for a in case["aspects"])
        / len(case["aspects"]),
    }


def validate_dataset(corpus, dataset):
    cases = dataset["cases"]
    if len({c["id"] for c in cases}) != len(cases) or {c["category"] for c in cases} != CATEGORIES:
        raise ValueError("Missing categories or duplicate cases")
    for course in corpus["courses"].values():
        es = course["evidence"]
        if len({e["evidence_id"] for e in es}) != len(es):
            raise ValueError("Duplicate Evidence")
        for e in es:
            if hashlib.sha256(e["text"].encode()).hexdigest() != e["content_hash"]:
                raise ValueError("Evidence content hash mismatch")
            Evidence(**{k: e[k] for k in ("evidence_id", "text", "start_ms", "end_ms")})
    for case in cases:
        es = {e["evidence_id"] for e in corpus["courses"][case["course"]]["evidence"] if e["retrievable"]}
        gold = {eid for aspect in case["aspects"] for eid in aspect["evidence_ids"]}
        if not gold <= es or not set(case["hard_negative_ids"]) <= es:
            raise ValueError("Gold/negative outside course")
        if gold & set(case["hard_negative_ids"]):
            raise ValueError("Positive is also hard negative")
        if case["answerable"] != bool(gold) or any(not a["evidence_ids"] for a in case["aspects"]):
            raise ValueError("Invalid answerability")
        if not case["answerable"] and not case["no_answer_reason"]:
            raise ValueError("Missing no-answer rationale")


def percentile(values, p):
    if not values or not 0 <= p <= 1:
        raise ValueError("Invalid percentile inputs")
    values = sorted(values)
    index = (len(values) - 1) * p
    low, high = math.floor(index), math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)


def verify_freeze(directory):
    freeze = json.loads((directory / "freeze.json").read_text())
    root = directory.resolve().parents[1]
    for name, expected in freeze["files"].items():
        if digest(root / name) != expected:
            raise ValueError(f"Frozen input/code changed: {name}; create a new candidate, retain old results")
    for name, expected in freeze.get("packages", {}).items():
        if version(name) != expected:
            raise ValueError(f"Frozen package changed: {name}")
    return freeze
