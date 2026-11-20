"""Offline checks for the L4 benchmark harness: no network, no provider, synthetic data only."""

import json
import multiprocessing
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from lecturelens_real_eval.l4 import (
    blind,
    citations,
    flash_judge,
    judge,
    pipeline,
    pricing,
    questions,
    scoring,
)
from lecturelens_real_eval.l4.ledger import BudgetExceeded, Ledger, LedgerError
from lecturelens_real_eval.l4.normalize import normalize
from lecturelens_real_eval.l4.runner import L4TutorStore, event_usage

# ---------------------------------------------------------------- pricing


def test_peak_window_and_cache_split():
    assert pricing.tier(datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc)) == "peak"  # Tuesday 01:00
    assert pricing.tier(datetime(2026, 11, 17, 4, 0, tzinfo=timezone.utc)) == "off_peak"
    assert pricing.tier(datetime(2026, 11, 17, 9, 59, tzinfo=timezone.utc)) == "peak"
    assert pricing.tier(datetime(2026, 11, 21, 7, 0, tzinfo=timezone.utc)) == "off_peak"  # Saturday
    at = datetime(2026, 11, 17, 7, 0, tzinfo=timezone.utc)
    split = {
        "prompt_tokens": 1000,
        "completion_tokens": 10,
        "prompt_cache_hit_tokens": 400,
        "prompt_cache_miss_tokens": 600,
    }
    assert pricing.cost_nano("deepseek-flash", split, at) == 400 * 6 + 600 * 300 + 10 * 1200
    # No split (or an inconsistent one): every prompt token at the miss rate.
    assert (
        pricing.cost_nano("deepseek-flash", {"prompt_tokens": 1000, "completion_tokens": 10}, at)
        == 1000 * 300 + 12000
    )
    bad = {**split, "prompt_cache_hit_tokens": 1}
    assert pricing.cost_nano("deepseek-flash", bad, at) == 1000 * 300 + 12000
    assert pricing.cost_nano("deepseek-flash", {"prompt_tokens": "1"}, at) is None
    assert (
        pricing.cost_nano("deepseek-v4-pro", {"prompt_tokens": 10, "completion_tokens": 10}, at)
        == 10 * 1320 + 10 * 3960
    )


# ---------------------------------------------------------------- ledger


def make_ledger(tmp_path, stop=1.0, cap=0.5):
    return Ledger(tmp_path / "ledger.jsonl", hard_stop_usd=stop, request_cap_usd=cap)


def test_ledger_reserve_settle_uncertain_release(tmp_path):
    ledger = make_ledger(tmp_path)
    a = ledger.reserve(phase="dev", arm="rag", unit="x#1", model="deepseek-flash", upper_nano=100_000_000)
    b = ledger.reserve(phase="dev", arm="rag", unit="y#1", model="deepseek-flash", upper_nano=200_000_000)
    c = ledger.reserve(phase="dev", arm="rag", unit="z#1", model="deepseek-flash", upper_nano=50_000_000)
    assert ledger.summary()["outstanding_nano"] == 350_000_000
    at = "2026-11-21T07:00:00+00:00"
    assert (
        ledger.settle(
            a,
            [{"model": "deepseek-flash", "at": at, "usage": {"prompt_tokens": 100, "completion_tokens": 10}}],
        )
        == 100 * 150 + 10 * 600
    )
    assert ledger.uncertain(b, "TIMEOUT") == 200_000_000
    ledger.release(c, "QA_SKIPPED_NO_EVIDENCE")
    totals = ledger.summary()
    assert totals == {
        "settled_nano": 21_000,
        "uncertain_nano": 200_000_000,
        "outstanding_nano": 0,
        "committed_nano": 200_021_000,
    }
    with pytest.raises(LedgerError):
        ledger.settle(a, [])
    with pytest.raises(LedgerError):
        ledger.release(b, "late")


def test_ledger_missing_usage_is_uncertain(tmp_path):
    ledger = make_ledger(tmp_path)
    unit = ledger.reserve(phase="dev", arm="study", unit="x#1", model="deepseek-flash", upper_nano=7)
    ledger.settle(unit, [{"model": "deepseek-flash", "at": "2026-11-21T07:00:00+00:00", "usage": None}])
    assert ledger.summary()["uncertain_nano"] == 7


def test_ledger_caps(tmp_path):
    ledger = make_ledger(tmp_path, stop=1.0, cap=0.5)
    with pytest.raises(BudgetExceeded, match="PER_REQUEST_CAP"):
        ledger.reserve(phase="dev", arm="judge", unit="u", model="deepseek-v4-pro", upper_nano=600_000_000)
    ledger.reserve(phase="dev", arm="judge", unit="u1", model="deepseek-v4-pro", upper_nano=500_000_000)
    ledger.reserve(phase="dev", arm="judge", unit="u2", model="deepseek-v4-pro", upper_nano=500_000_000)
    with pytest.raises(BudgetExceeded, match="HARD_STOP"):
        ledger.reserve(phase="dev", arm="judge", unit="u3", model="deepseek-v4-pro", upper_nano=1)
    with pytest.raises(LedgerError):
        ledger.reserve(phase="dev", arm="judge", unit="u4", model="deepseek-v4-pro", upper_nano=0)


def _reserve_many(path, out):
    ledger = Ledger(path, hard_stop_usd=1.0, request_cap_usd=1.0)
    won = 0
    for n in range(20):
        try:
            ledger.reserve(phase="dev", arm="rag", unit=str(n), model="deepseek-flash", upper_nano=60_000_000)
            won += 1
        except BudgetExceeded:
            pass
    out.put(won)


def test_ledger_never_admits_past_the_stop_across_processes(tmp_path):
    path = tmp_path / "ledger.jsonl"
    queue = multiprocessing.get_context("fork").Queue()
    workers = [
        multiprocessing.get_context("fork").Process(target=_reserve_many, args=(path, queue))
        for _ in range(4)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    admitted = sum(queue.get() for _ in workers)
    assert admitted == 16  # floor(1.0 USD / 0.06 USD)
    assert Ledger(path, hard_stop_usd=1, request_cap_usd=1).summary()["outstanding_nano"] == 16 * 60_000_000


# ---------------------------------------------------------------- scoring


def row(
    path,
    item,
    lecture,
    answerable,
    *,
    rep=1,
    status="ok",
    abstained=False,
    verdict="CORRECT",
    lenient=1.0,
    error=False,
    claims=(2, 2),
    pairs=(2, 2),
    distinct=(1, 1),
    hit=True,
    cost=100,
    latency=1000,
):
    return {
        "path": path,
        "rep": rep,
        "item_id": item,
        "lecture_id": lecture,
        "answerable": answerable,
        "status": status,
        "abstained": abstained,
        "verdict": verdict,
        "vital_lenient": lenient,
        "material_error": error,
        "claims_supported": claims[0],
        "claims_total": claims[1],
        "citation_pairs_precise": pairs[0],
        "citation_pairs_total": pairs[1],
        "citations_relevant": distinct[0],
        "citations_distinct": distinct[1],
        "gold_evidence_hit": hit if answerable else None,
        "cost_nano": cost,
        "latency_ms": latency,
    }


NOTHING = {"claims": (0, 0), "pairs": (0, 0), "distinct": (0, 0), "lenient": 0.0}


def fixture_rows():
    return [
        row("rag", "a1", "L1", True),
        row(
            "rag",
            "a2",
            "L1",
            True,
            verdict="INCORRECT",
            lenient=0.75,
            error=True,
            claims=(1, 2),
            pairs=(1, 6),
            distinct=(1, 3),
            hit=False,
        ),
        row("rag", "a3", "L2", True, abstained=True, verdict=None, hit=None, **NOTHING),
        row("rag", "u1", "L2", False, abstained=True, verdict=None, **NOTHING),
        row("tutor", "a1", "L1", True, status="failed", verdict=None, hit=None, latency=5000, **NOTHING),
        row("tutor", "a2", "L1", True),
        row("tutor", "a3", "L2", True),
        row("tutor", "u1", "L2", False, verdict="INCORRECT", lenient=0.0),
    ]


def test_metric_arithmetic_keeps_failures_and_abstentions():
    report = scoring.summarize(fixture_rows(), draws=200)["metrics"]

    def estimate(metric, path):
        return report[metric]["paths"][path]["estimate"]

    assert estimate("strict_correct", "rag") == pytest.approx(1 / 3)
    assert estimate("strict_correct", "tutor") == pytest.approx(2 / 3)  # failure counts as incorrect
    # Lenient: the abstained answerable item stays in the denominator with 0 credit.
    assert estimate("vital_lenient", "rag") == pytest.approx((1 + 0.75 + 0) / 3)
    assert estimate("vital_lenient", "tutor") == pytest.approx((0 + 1 + 1) / 3)
    assert estimate("material_error", "rag") == pytest.approx(1 / 2)  # answered answerable responses only
    # Citation metrics are micro-averaged over answered responses.
    assert estimate("citation_recall", "rag") == pytest.approx(3 / 4)
    assert estimate("citation_precision", "rag") == pytest.approx(3 / 8)
    assert estimate("citation_precision_distinct", "rag") == pytest.approx(2 / 4)
    assert estimate("citation_recall", "tutor") == pytest.approx(6 / 6)  # u1 answered, so it counts
    assert estimate("gold_evidence_hit", "rag") == pytest.approx(1 / 2)
    assert estimate("abstain_recall", "rag") == 1.0
    assert estimate("abstain_recall", "tutor") == 0.0
    assert estimate("false_refusal", "rag") == pytest.approx(1 / 3)
    assert estimate("abstain_accuracy", "rag") == pytest.approx(3 / 4)
    assert estimate("abstain_accuracy", "tutor") == pytest.approx(2 / 4)  # failure is a wrong decision
    assert estimate("failure_rate", "tutor") == pytest.approx(1 / 4)
    diff = report["strict_correct"]["differences"]["rag-tutor"]
    assert diff["estimate"] == pytest.approx(1 / 3 - 2 / 3)
    assert diff["level"] == pytest.approx(0.95)  # one pair in this fixture: no Bonferroni split


def test_gold_evidence_hit_uses_vital_nugget_ranges():
    item = {
        "nuggets": [
            {"importance": "vital", "cues": [{"start": "01:00", "end": "01:30"}]},
            {"importance": "okay", "cues": [{"start": "05:00", "end": "05:30"}]},
        ]
    }
    evidence = {
        "near": {"startMs": 80_000, "endMs": 140_000},
        "okay-only": {"startMs": 300_000, "endMs": 320_000},
        "inside": {"startMs": 65_000, "endMs": 70_000},
        "touching": {"startMs": 90_000, "endMs": 120_000},  # starts where the cue ends: no overlap
        "far": {"startMs": 0, "endMs": 59_000},
    }
    assert scoring.gold_evidence_hit(item, ["near"], evidence)
    assert scoring.gold_evidence_hit(item, ["far", "inside"], evidence)
    assert not scoring.gold_evidence_hit(item, ["touching"], evidence)
    assert not scoring.gold_evidence_hit(item, ["okay-only", "far"], evidence)
    assert not scoring.gold_evidence_hit(item, ["missing"], evidence)
    assert not scoring.gold_evidence_hit(item, [], evidence)


def test_bootstrap_is_seeded_and_brackets_the_estimate():
    data = fixture_rows()
    first = scoring.summarize(data, draws=500)
    again = scoring.summarize(data, draws=500)
    assert first == again
    entry = first["metrics"]["strict_correct"]["paths"]["tutor"]
    assert entry["ci95"][0] <= entry["estimate"] <= entry["ci95"][1]
    _, weights = scoring.bootstrap_weights(data, draws=50)
    # Stratified: lecture L1 (a1, a2) always contributes 2 draws, L2 (a3, u1) also 2.
    assert (weights[:, :2].sum(axis=1) == 2).all() and (weights[:, 2:].sum(axis=1) == 2).all()


def test_three_paths_use_bonferroni_and_repetition_ranges():
    data = fixture_rows() + [
        row("study", i, lec, a)
        for i, lec, a in [("a1", "L1", True), ("a2", "L1", True), ("a3", "L2", True), ("u1", "L2", False)]
    ]
    data += [dict(r, rep=2, verdict="INCORRECT") for r in data if r["path"] == "study"]
    report = scoring.summarize(data, draws=200)
    assert set(report["metrics"]["strict_correct"]["differences"]) == {
        "rag-study",
        "rag-tutor",
        "study-tutor",
    }
    assert report["metrics"]["strict_correct"]["differences"]["rag-study"]["level"] == pytest.approx(
        1 - 0.05 / 3
    )
    assert scoring.repetition_range(data, "strict_correct")["study"] == [0.0, 1.0]


def test_small_statistics():
    assert scoring.nearest_rank([5, 1, 3, 2, 4], 0.5) == 3
    assert scoring.nearest_rank([5, 1, 3, 2, 4], 0.95) == 5
    assert scoring.nearest_rank(list(range(1, 21)), 0.95) == 19
    assert scoring.nearest_rank([], 0.5) is None
    low, high = scoring.wilson(8, 10)
    assert 0.49 < low < 0.5 and 0.94 < high < 0.95
    assert scoring.mcnemar_exact(0, 0) == 1.0
    assert scoring.mcnemar_exact(0, 6) == pytest.approx(2 / 64)
    assert scoring.cohen_kappa(["a", "b", "a", "a"], ["a", "b", "a", "a"]) == 1.0
    assert scoring.cohen_kappa(["a", "b", "a", "b"], ["a", "a", "b", "b"]) == pytest.approx(0.0)
    paired = scoring.mcnemar_pairs(fixture_rows())
    assert paired["rag-tutor"] == {"n": 3, "only_first": 1, "only_second": 2, "p_exact": 1.0}


def test_latency_and_cost_include_failures():
    out = scoring.latency_cost(fixture_rows(), draws=100)
    assert out["tutor"]["p95_ms"] == 5000  # the failed attempt stays in the latency sample
    assert out["rag"]["mean_cost_usd"] == pytest.approx(100 / 1e9)
    assert out["rag"]["p50_ms_ci95"][0] <= out["rag"]["p50_ms"] <= out["rag"]["p50_ms_ci95"][1]


# ---------------------------------------------------------------- question freeze


RULES = {
    "dev_lecture": {"answerable": {"definition_or_fact": 1}, "should_abstain": {"out_of_domain": 1}},
    "holdout_lecture": {"answerable": {"definition_or_fact": 1}, "should_abstain": {"out_of_domain": 1}},
}


def items(split):
    prefix = "d" if split == "dev" else "h"
    return [
        {
            "item_id": f"{prefix}-x01-01",
            "lecture_id": f"{split}-lec",
            "position": 1,
            "language": "zh",
            "category": "definition_or_fact",
            "answerable": True,
            "question": "问题？",
            "nuggets": [
                {
                    "id": "N1",
                    "importance": "vital",
                    "text": "p",
                    "cues": [{"start": "00:01", "end": "00:31", "quote": "the quote"}],
                },
                {
                    "id": "N2",
                    "importance": "okay",
                    "text": "detail",
                    "cues": [{"start": "00:01", "end": "00:31", "quote": "Here is"}],
                },
            ],
        },
        {
            "item_id": f"{prefix}-x01-02",
            "lecture_id": f"{split}-lec",
            "position": 2,
            "language": "en",
            "category": "out_of_domain",
            "answerable": False,
            "question": "Q?",
            "rationale": "r",
            "search_terms": ["a", "b", "c"],
        },
    ]


def freeze_root(tmp_path):
    (tmp_path / "questions").mkdir()
    (tmp_path / "sources").mkdir()
    (tmp_path / "PLAN.json").write_text(json.dumps({"question_set": {"fixed_rules": RULES}}))
    (tmp_path / "sources/assets.lock.json").write_text("{}")
    (tmp_path / "audit.json").write_text("{}")
    (tmp_path / "transcripts").mkdir()
    for split in ("dev", "holdout"):
        (tmp_path / f"transcripts/{split}-lec.txt").write_text("[00:01-00:31] Here is the quote.\n")
        (tmp_path / f"questions/questions.{split}.json").write_text(
            json.dumps({"split": split, "items": items(split)})
        )
    return tmp_path


def test_freeze_round_trip_and_tamper(tmp_path):
    root = freeze_root(tmp_path)
    (root / "audit-2.json").write_text('{"round": 2}')
    questions.write_freeze(root, audit_paths=[root / "audit.json", root / "audit-2.json"])
    record = json.loads((root / "FREEZE.json").read_text())
    assert [a["file"] for a in record["gold_audits"]] == ["audit.json", "audit-2.json"]
    assert record["gold_audits"][1]["sha256"] == questions.file_sha(root / "audit-2.json")
    assert [i["item_id"] for i in questions.load_frozen(root, "holdout")] == ["h-x01-01", "h-x01-02"]
    with pytest.raises(FileExistsError):
        questions.write_freeze(root, audit_paths=[root / "audit.json"])
    path = root / "questions/questions.holdout.json"
    data = json.loads(path.read_text())
    data["items"][0]["nuggets"][0]["text"] = "edited after freeze"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="FREEZE_QUESTIONS_CHANGED"):
        questions.load_frozen(root, "holdout")
    (root / "PLAN.json").write_text(json.dumps({"question_set": {"fixed_rules": RULES}, "edited": True}))
    with pytest.raises(ValueError, match="FREEZE_PLAN_CHANGED"):
        questions.load_frozen(root, "dev")


def test_freeze_rejects_rule_violations(tmp_path):
    root = freeze_root(tmp_path)
    data = {"split": "dev", "items": items("dev")}
    data["items"][1]["language"] = "zh"
    (root / "questions/questions.dev.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="language rule"):
        questions.write_freeze(root, audit_paths=[root / "audit.json"])
    assert not (root / "FREEZE.json").exists()
    bad = {"split": "dev", "items": [items("dev")[0]]}
    assert any("category counts" in e for e in questions.check_set(bad, RULES))
    with pytest.raises(ValueError, match="gold-audit"):
        questions.write_freeze(root, audit_paths=[])


def test_nugget_structure_rules():
    good = items("holdout")[0]
    assert questions.nugget_errors(good) == []

    def errors(**change):
        item = json.loads(json.dumps(good))
        for index, fields in change.items():
            item["nuggets"][int(index[1:])].update(fields)
        return questions.nugget_errors(item)

    assert any("vital nugget count" in e for e in errors(n0={"importance": "okay"}))
    assert any("importance" in e for e in errors(n1={"importance": "nice"}))
    assert any("N1..Nk" in e for e in errors(n1={"id": "N3"}))
    assert any("without text" in e for e in errors(n1={"text": " "}))
    four = json.loads(json.dumps(good))
    four["nuggets"] = [dict(good["nuggets"][0], id=f"N{k}") for k in range(1, 5)]
    assert any("vital nugget count must be 1-3" in e for e in questions.nugget_errors(four))
    assert questions.nugget_errors({**good, "nuggets": []}) == ["h-x01-01: answerable item without nuggets"]
    abstain = {"split": "holdout", "items": [dict(items("holdout")[1], nuggets=good["nuggets"])]}
    assert any("should-abstain item has nuggets" in e for e in questions.check_set(abstain, RULES))


def test_freeze_refuses_a_quote_outside_its_cue(tmp_path):
    root = freeze_root(tmp_path)
    data = {"split": "holdout", "items": items("holdout")}
    data["items"][0]["nuggets"][1]["cues"][0]["quote"] = "a quote the lecture never says"
    (root / "questions/questions.holdout.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="quote not in the cited windows"):
        questions.write_freeze(root, audit_paths=[root / "audit.json"])
    assert not (root / "FREEZE.json").exists()


# ---------------------------------------------------------------- gold citations

# Synthetic captions written for this test; they quote no real lecture.
CAPTIONS = """[00:09-00:40] In this example the sorting chart is known as a
[00:40-01:14] routing chart. But a flow chart is a name for another idea.
[01:20-01:50] Several inputs don't count, and some -- count only some of the time.
"""


def cue(start, end, quote):
    return {"start": start, "end": end, "quote": quote}


def test_citation_windows_parse_and_reject_malformed_lines():
    windows = citations.parse_windows(CAPTIONS)
    assert [w[:2] for w in windows] == [("00:09", "00:40"), ("00:40", "01:14"), ("01:20", "01:50")]
    with pytest.raises(ValueError, match="line 2"):
        citations.parse_windows("[00:01-00:02] ok\nnot a window\n")


def test_citation_cue_rules():
    windows = citations.parse_windows(CAPTIONS)
    ok = citations.check_cue
    # Case, punctuation and "--" are ignored; the words and their order are not.
    assert ok(cue("01:20", "01:50", "several inputs DON'T count, and some count only"), windows) is None
    assert ok(cue("01:20", "01:50", "count only some part"), windows) == "quote not in the cited windows"
    # A quote across a window boundary must name both windows ...
    spanning = "known as a routing chart"
    assert ok(cue("00:40", "01:14", spanning), windows) == "quote not in the cited windows"
    assert ok(cue("00:09", "01:14", spanning), windows) is None
    # ... and a cue may not be wider than its quote (one window off is an error, not a tolerance).
    assert ok(cue("00:09", "01:14", "a flow chart is a name"), windows) == "cue wider than the quote"
    assert ok(cue("00:40", "01:50", "a flow chart is a name"), windows) == "cue wider than the quote"
    # Labels must be real window boundaries.
    assert "not a window start" in ok(cue("00:10", "00:40", "this example the sorting"), windows)
    assert "not a window end" in ok(cue("00:40", "01:20", "routing chart"), windows)
    assert ok(cue("00:09", "00:40", " -- "), windows) == "empty quote"


def test_citation_locate_and_item_errors():
    windows = citations.parse_windows(CAPTIONS)
    assert citations.locate("known as a routing chart", windows) == [("00:09", "01:14")]
    assert citations.locate("flow chart", windows) == [("00:40", "01:14")]
    item = {
        "item_id": "h-x01-01",
        "lecture_id": "lec",
        "nuggets": [
            {"id": "N1", "cues": [cue("00:40", "01:14", "routing chart")]},
            {"id": "N2", "cues": [cue("00:40", "01:14", "known as a routing chart")]},
            {"id": "N3", "cues": []},
        ],
    }
    abstain = {"item_id": "h-x01-02", "lecture_id": "lec", "search_terms": ["x"]}
    errors = citations.check_items([item, abstain], {"lec": windows})
    assert errors == [
        "h-x01-01 N2 cue1 00:40-01:14: quote not in the cited windows",
        "h-x01-01 N3: nugget without cue",
    ]


# ---------------------------------------------------------------- blind packets


def responses():
    out = []
    for path in ("rag", "tutor", "study"):
        for rep in (1, 2):
            out.append(
                {
                    "path": path,
                    "rep": rep,
                    "item_id": "h-x01-01",
                    "text": f"{path} answer [C1]",
                    "citations": [{"cid": "C1", "text": "excerpt"}],
                    "citation_scope": "inline",
                    "abstained": False,
                }
            )
    return out


def test_packet_hides_path_and_reveal_round_trips():
    packet, mapping = blind.build(responses(), items("holdout"), seed=7)
    serialized = json.dumps(packet)
    for secret in ('"rag"', '"tutor"', '"study"', '"rep"', "definition_or_fact", "cost", "latency"):
        assert secret not in serialized
    assert blind.build(responses(), items("holdout"), seed=7) == (packet, mapping)
    decisions = {e["response_id"]: {"verdict": "CORRECT"} for e in packet["entries"]}
    joined = blind.reveal(packet, mapping, decisions)
    assert sorted((r["path"], r["rep"]) for r in joined) == sorted((r["path"], r["rep"]) for r in responses())
    blind.check_ids(decisions)


def test_reveal_refuses_tampering_and_gaps():
    packet, mapping = blind.build(responses(), items("holdout"), seed=7)
    decisions = {e["response_id"]: {} for e in packet["entries"]}
    tampered = json.loads(json.dumps(packet))
    tampered["entries"][0]["response"]["text"] = "changed"
    with pytest.raises(ValueError, match="REVEAL_PACKET_MISMATCH"):
        blind.reveal(tampered, mapping, decisions)
    partial = dict(list(decisions.items())[1:])
    with pytest.raises(ValueError, match="REVEAL_DECISIONS_INCOMPLETE"):
        blind.reveal(packet, mapping, partial)
    wrong = {
        "packet_sha256": mapping["packet_sha256"],
        "responses": dict(list(mapping["responses"].items())[1:]),
    }
    with pytest.raises(ValueError, match="REVEAL_MAPPING_MISMATCH"):
        blind.reveal(packet, wrong, decisions)


def test_agreement_sample_is_stratified_and_withholds_verdicts():
    many = [dict(r, item_id="h-x01-01", rep=rep) for r in responses()[:1] for rep in range(1, 11)]
    many += [dict(r, path="study", rep=rep) for r in responses()[:1] for rep in range(1, 11)]
    packet, mapping = blind.build(many, items("holdout"), seed=3)
    decisions = {e["response_id"]: {"verdict": "INCORRECT"} for e in packet["entries"]}
    review, key = blind.agreement_sample(packet, mapping, decisions, seed=3)
    assert len(review["entries"]) == 4  # ceil(20%) of 10 per path
    assert {mapping["responses"][e["response_id"]]["path"] for e in review["entries"]} == {"rag", "study"}
    assert "INCORRECT" not in json.dumps(review) and '"rag"' not in json.dumps(review)
    assert key["packet_sha256"] == blind.sha256(review) and len(key["judge"]) == 4


# ---------------------------------------------------------------- judge decisions


def entry(scope="inline", declared=False):
    packet, _ = blind.build(
        [dict(responses()[0], citation_scope=scope, abstained=declared)], items("holdout"), seed=1
    )
    return next(e for e in packet["entries"])


def decision(**over):
    base = {
        "nuggets": [{"id": "N1", "label": "support"}, {"id": "N2", "label": "none"}],
        "material_error": False,
        "claims": [
            {
                "claim": "c",
                "cited": ["C1"],
                "support": "full",
                "citations": [{"cid": "C1", "relevance": "alone"}],
            }
        ],
        "abstention_leak": False,
        "verdict": "CORRECT",
    }
    return json.dumps({**base, **over})


def claim(support, *rated, text="c"):
    return {
        "claim": text,
        "cited": [cid for cid, _ in rated],
        "support": support,
        "citations": [{"cid": cid, "relevance": rel} for cid, rel in rated],
    }


def test_packet_shows_nuggets_with_importance_not_categories():
    gold = entry()["gold"]
    assert [(n["id"], n["importance"]) for n in gold["nuggets"]] == [("N1", "vital"), ("N2", "okay")]
    assert gold["nuggets"][0]["caption_anchor"] == ["the quote"]


def test_judge_validation_accepts_consistent_and_rejects_inconsistent():
    out = judge.validate(entry(), decision())
    # The okay nugget is unsupported, yet the item is strictly correct: only vital nuggets decide.
    assert out["verdict"] == "CORRECT" and out["vital_supported"] == out["vital_total"] == 1
    assert out["vital_lenient"] == 1.0 and out["all_lenient"] == 0.5
    with pytest.raises(ValueError, match="inconsistent"):
        judge.validate(
            entry(), decision(nuggets=[{"id": "N1", "label": "partial"}, {"id": "N2", "label": "none"}])
        )
    with pytest.raises(ValueError, match="inconsistent"):
        judge.validate(entry(), decision(material_error=True))
    with pytest.raises(ValueError, match="inconsistent"):
        judge.validate(entry(declared=True), decision())
    with pytest.raises(ValueError, match="nugget ids"):
        judge.validate(entry(), decision(nuggets=[{"id": "N1", "label": "support"}]))
    with pytest.raises(ValueError, match="nugget label"):
        judge.validate(
            entry(), decision(nuggets=[{"id": "N1", "label": "yes"}, {"id": "N2", "label": "none"}])
        )
    with pytest.raises(ValueError, match="invalid claim citations"):
        judge.validate(entry(), decision(claims=[claim("full", ("C9", "alone"))]))
    with pytest.raises(ValueError, match="exactly the cited labels"):
        judge.validate(entry(), decision(claims=[{**claim("full", ("C1", "alone")), "citations": []}]))
    with pytest.raises(ValueError, match="supports the claim alone"):
        judge.validate(entry(), decision(claims=[claim("partial", ("C1", "alone"))]))
    with pytest.raises(ValueError, match="without a citation"):
        judge.validate(entry(), decision(claims=[claim("full")]))
    with pytest.raises(ValueError, match="at most 6"):
        judge.validate(entry(), decision(claims=[claim("none")] * 7))


def test_lenient_score_gives_partial_half_credit():
    out = judge.validate(
        entry(),
        decision(
            nuggets=[{"id": "N1", "label": "partial"}, {"id": "N2", "label": "support"}],
            verdict="INCORRECT",
        ),
    )
    assert out["vital_lenient"] == 0.5 and out["all_lenient"] == 0.75 and out["vital_supported"] == 0


@pytest.mark.parametrize(
    ("label", "material_error", "declared", "unreadable", "verdict"),
    [
        ("support", False, False, False, "CORRECT"),
        ("partial", False, False, False, "INCORRECT"),
        ("none", False, False, False, "INCORRECT"),
        ("support", True, False, False, "INCORRECT"),
        ("support", False, True, False, "INCORRECT"),
        ("support", False, False, True, "UNDETERMINED"),
    ],
)
def test_flash_judge_derives_the_same_strict_verdict(label, material_error, declared, unreadable, verdict):
    case = entry(declared=declared)
    raw = json.loads(
        decision(
            nuggets=[{"id": "N1", "label": label}, {"id": "N2", "label": "none"}],
            material_error=material_error,
            verdict=verdict,
        )
    )
    expected = judge.validate(case, json.dumps(raw))
    del raw["verdict"]
    raw["unreadable"] = unreadable
    assert flash_judge.validate(case, json.dumps(raw)) == expected
    with pytest.raises(ValueError, match="verdict must be derived"):
        flash_judge.validate(case, json.dumps({**raw, "verdict": "CORRECT"}))


def test_flash_judge_preserves_claims_errors_and_rubric():
    case = entry()
    grouped = [
        claim("partial", ("C1", "irrelevant"), text="Supported first fact and unsupported second fact"),
        *[claim("none", text=f"Uncited assertion {n}") for n in range(judge.MAX_CLAIMS - 1)],
    ]
    reason = "A substantive contradiction. " * 25
    raw = json.loads(decision(claims=grouped, material_error=True, material_error_reason=reason))
    del raw["verdict"]
    raw["unreadable"] = False
    result = flash_judge.validate(case, json.dumps(raw))
    assert result["claims"] == grouped and result["verdict"] == "INCORRECT"
    assert result["material_error_reason"] == reason
    raw["claims"].append(claim("none", text="Another assertion"))
    with pytest.raises(ValueError, match=f"at most {judge.MAX_CLAIMS}"):
        flash_judge.validate(case, json.dumps(raw))

    facts = flash_judge.request_body(case)
    assert facts["thinking"] == {"type": "disabled"} and facts["model"] == "deepseek-flash"
    assert facts["messages"][1] == judge.request_body(case)["messages"][1]
    assert f"at most {judge.MAX_CLAIMS}" in facts["messages"][0]["content"]
    non_answerable = {**case, "gold": {"answerable": False}}
    raw.update(nuggets=[], claims=[], material_error=False)
    assert flash_judge.validate(non_answerable, json.dumps(raw))["verdict"] == "INCORRECT"


def test_alce_citation_recall_and_precision_counts():
    claims = [
        claim("full", ("C1", "alone"), ("C2", "irrelevant")),  # one precise, one over-citation
        claim("full", ("C1", "needed"), ("C3", "needed")),  # both needed together: both precise
        claim("partial", ("C2", "needed")),  # unsupported claim: its citation is imprecise
        claim("none"),  # no citation at all
    ]
    counts = judge.citation_counts(claims)
    assert counts == {
        "claims_supported": 2,
        "claims_total": 4,
        "citation_pairs_precise": 3,
        "citation_pairs_total": 5,
        "citations_relevant": 2,  # C1 and C3; C2 never helps a fully supported claim
        "citations_distinct": 3,
    }
    assert judge.citation_counts([]) == {
        "claims_supported": 0,
        "claims_total": 0,
        "citation_pairs_precise": 0,
        "citation_pairs_total": 0,
        "citations_relevant": 0,
        "citations_distinct": 0,
    }


def test_response_scope_citations_attach_to_every_claim():
    out = judge.validate(
        entry("response"), decision(claims=[{**claim("full", ("C1", "alone")), "cited": []}])
    )
    assert out["claims"][0]["cited"] == ["C1"] and out["claims_supported"] == 1
    assert out["citation_pairs_precise"] == out["citation_pairs_total"] == 1


def test_undetermined_keeps_the_vital_denominator():
    out = judge.undetermined(entry(), "INVALID")
    assert out["vital_total"] == 1 and out["vital_lenient"] == 0.0 and out["claims_total"] == 0


def test_judge_request_and_reservation_bound():
    body = judge.request_body(entry())
    assert body["model"] == "deepseek-v4-pro" and body["thinking"] == {"type": "enabled"}
    assert body["max_tokens"] == judge.MAX_TOKENS == 24576
    assert '"rag"' not in body["messages"][1]["content"]
    assert judge.reservation_nano(body) == pricing.upper_nano(
        "deepseek-v4-pro", len(blind.canonical(body)), 24576
    )


def test_study_event_usage_reads_top_level_token_counts():
    payload = {"purpose": "decision", "prompt_tokens": 1048, "completion_tokens": 121}
    assert event_usage(payload) == {"prompt_tokens": 1048, "completion_tokens": 121}
    assert event_usage({"usage": {"prompt_tokens": 1, "completion_tokens": 2}}) == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
    }
    assert event_usage({"prompt_tokens": 10}) is None  # a failed call without both counts stays uncertain
    assert event_usage(None) is None


# ---------------------------------------------------------------- normalization


def test_inline_citations_are_renumbered_and_text_cleaned():
    evidence = {"e" * 64: "first excerpt", "f" * 64: "second excerpt"}
    text = f"## Answer\n**Bold** claim [{'f' * 64}] and more [{'e' * 64}] then [{'f' * 64}]."
    out = normalize(text, ["e" * 64, "f" * 64], evidence, inline=True, labels=("Answer",))
    assert out["text"] == "Answer\nBold claim [C1] and more [C2] then [C1]."
    assert [c["text"] for c in out["citations"]] == ["second excerpt", "first excerpt"]
    assert out["citation_scope"] == "inline"
    rag = normalize("Plain answer.", ["e" * 64], evidence)
    assert rag["citation_scope"] == "response" and rag["citations"] == [
        {"cid": "C1", "text": "first excerpt"}
    ]
    with pytest.raises(KeyError):
        normalize("x", ["0" * 64], evidence)


# ---------------------------------------------------------------- Tutor admission adapter


class FakeLedger:
    def __init__(self):
        self.calls = []

    def reserve(self, **kw):
        self.calls.append(("reserve", kw))
        return "r1"

    def settle(self, reservation, calls):
        self.calls.append(("settle", reservation, calls))

    def uncertain(self, reservation, reason, calls=()):
        self.calls.append(("uncertain", reservation, reason))


def test_tutor_adapter_reserves_before_and_settles_after():
    store = L4TutorStore()
    ledger = FakeLedger()
    store.setup_l4(ledger, offline=True)
    assert store.grant.mode == "offline-fake"
    store.l4_unit = ("dev-rep1", "d-ai10-01#1")
    store.reserve(None, {}, {"turn_id": "t1"}, {"reservation": 10_000}, "sha")
    assert ledger.calls[0][1]["upper_nano"] == pricing.upper_nano("deepseek-flash", 10_000, 4096)
    usage = {"prompt_tokens": 5, "completion_tokens": 1}
    assert store.settle("t1", "sha", SimpleNamespace(usage=usage, error=None)) is None
    assert ledger.calls[1][0] == "settle" and ledger.calls[1][2][0]["usage"] == usage
    store.l4_reservations["t2"] = "r2"
    assert (
        store.settle("t2", "sha", SimpleNamespace(usage=None, error="TUTOR_FLASH_TIMEOUT"))
        == "TUTOR_FLASH_TIMEOUT"
    )
    assert ledger.calls[2] == ("uncertain", "r2", "TUTOR_FLASH_TIMEOUT")


def test_current_tutor_has_a_separate_identity_from_frozen_l4():
    """The published L4 result belongs to the historical build named by its PLAN."""
    from lecturelens_real_eval.tutor.flash_ledger import build_digest

    assert build_digest() != "4fcf204f5aed4cb3046f340105083d008dc916829f155877ed834d344971ecaf"


# ---------------------------------------------------------------- holdout execution (PLAN v4 revision 3)


def test_judge_limit_falls_back_once_then_stops():
    events = []
    limit = pipeline.AdaptiveLimit(8, 4, events.append)
    for status in (200, 429, 503):
        limit.record(status)
    assert limit.limit == 8 and limit.degraded is None
    limit.record(None)  # third provider error in a row (transport)
    assert limit.limit == 4 and events and events[0]["reason"] == "3 consecutive provider errors"
    for _ in range(2):
        limit.record(500)
    with pytest.raises(pipeline.ProviderErrorsPersist):
        limit.record(502)
    with pytest.raises(pipeline.ProviderErrorsPersist):
        with limit:
            pass


def test_judge_limit_error_rate_needs_a_denominator():
    limit = pipeline.AdaptiveLimit(8, 4)
    for k in range(19):
        limit.record(429 if k in (3, 9) else 200)
    assert limit.degraded is None  # 2/19 but below the 20-attempt minimum
    limit.record(200)
    assert limit.degraded["reason"] == "provider error rate 2/20" and limit.limit == 4
    limit.record(400)  # a client error is not a provider error
    assert limit.errors == 0


def test_judge_limit_bounds_requests_in_flight():
    limit = pipeline.AdaptiveLimit(2, 1)
    peak, now, lock = [0], [0], threading.Lock()

    def worker():
        with limit:
            with lock:
                now[0] += 1
                peak[0] = max(peak[0], now[0])
            time.sleep(0.02)
            with lock:
                now[0] -= 1

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 2


def test_inflight_counter_is_shared_and_ignores_dead_processes(tmp_path):
    path = tmp_path / "inflight.json"
    assert pipeline.judge_inflight(path) == 0
    counter = pipeline.InflightCounter(path)
    with counter:
        with counter:
            assert pipeline.judge_inflight(path) == 2
        assert pipeline.judge_inflight(path) == 1
    assert pipeline.judge_inflight(path) == 0
    path.write_text(json.dumps({"999999999": 3}))  # a crashed judge process
    assert pipeline.judge_inflight(path) == 0


def write_packet(base, response_list, seed):
    packet, mapping = blind.build(response_list, items("holdout"), seed=seed)
    base.mkdir(parents=True)
    (base / "packet.json").write_text(json.dumps(packet))
    (base / "judge-only-mapping.json").write_text(json.dumps(mapping))
    decisions = {e["response_id"]: {"verdict": "INCORRECT"} for e in packet["entries"]}
    (base / "decisions.json").write_text(json.dumps(decisions))
    return packet, mapping


def test_verify_sources_requires_complete_disjoint_packets(tmp_path):
    rep1 = [r for r in responses() if r["rep"] == 1]
    rep2 = [r for r in responses() if r["rep"] == 2]
    write_packet(tmp_path / "rep1", rep1, 1)
    write_packet(tmp_path / "rep2", rep2, 2)
    ok = {(r["path"], r["rep"], r["item_id"]) for r in rep1 + rep2}
    report = pipeline.verify_sources(tmp_path, ["rep1", "rep2"], ok)
    assert report["rep1"] == {"reps": [1], "judged": 3, "undetermined": 0}
    with pytest.raises(ValueError, match="VERIFY_UNJUDGED"):
        pipeline.verify_sources(tmp_path, ["rep1"], ok)
    with pytest.raises(ValueError, match="VERIFY_RECORDS_MISMATCH"):
        pipeline.verify_sources(tmp_path, ["rep1", "rep2"], ok | {("study", 2, "h-x01-02")})
    decisions = json.loads((tmp_path / "rep2/decisions.json").read_text())
    decisions.pop(next(iter(decisions)))
    (tmp_path / "rep2/decisions.json").write_text(json.dumps(decisions))
    with pytest.raises(ValueError, match="REVEAL_DECISIONS_INCOMPLETE"):
        pipeline.verify_sources(tmp_path, ["rep1", "rep2"], ok)


def test_agreement_is_split_by_course_and_covers_twenty_percent():
    lectures = {"ai": "mit-6.034-f10-lec11", "bio": "mit-7.016-f18-lec10", "stat": "mit-18.650-f16-lec03"}
    many = [
        dict(responses()[0], path=path, item_id=f"h-{course}-{k:02d}", rep=1)
        for course in lectures
        for k in range(10)
        for path in ("rag", "tutor", "study")
    ]
    gold = [dict(items("holdout")[0], item_id=r["item_id"]) for r in many[::3]]
    packet, mapping = blind.build(many, gold, seed=5)
    decisions = {e["response_id"]: {"verdict": "CORRECT"} for e in packet["entries"]}
    lectures = {r["item_id"]: lectures[r["item_id"].split("-")[1]] for r in many}
    out = pipeline.agreement_by_course(packet["entries"], mapping["responses"], decisions, lectures, seed=5)
    assert sorted(out) == ["18.650", "6.034", "7.016"]
    sizes = [len(review["entries"]) for review, _ in out.values()]
    assert sizes == [6, 6, 6] and sum(sizes) / len(many) >= 0.2  # ceil(20%) of 10 per path and course
    for course, (review, key) in out.items():
        text = json.dumps(review)
        assert '"rag"' not in text and "CORRECT" not in text and key["packet_sha256"] == blind.sha256(review)
        assert {lectures[where["item_id"]] for where in key["paths"].values()} == {
            next(v for v in lectures.values() if v.split("-")[1] == course)
        }
    again = pipeline.agreement_by_course(packet["entries"], mapping["responses"], decisions, lectures, seed=5)
    assert again == out


def test_cost_gate_projection_counts_unjudged_responses():
    projected = pipeline.projected_spend(
        committed_nano=10_000_000_000,
        pending_judge=100,
        judge_mean_nano=25_000_000,
        remaining_reps=2,
        product_rep_nano=1_000_000_000,
        entries_per_rep=260,
    )
    assert projected == 10_000_000_000 + 100 * 25_000_000 + 2 * (1_000_000_000 + 260 * 25_000_000)


def test_account_refusal_stops_every_thread():
    limit = pipeline.AdaptiveLimit(6, 4)
    entered = threading.Event()
    release = threading.Event()
    outcome = []

    def in_flight():
        with limit:
            entered.set()
            release.wait(2)
        outcome.append("finished")

    first = threading.Thread(target=in_flight)
    first.start()
    entered.wait(2)
    limit.stop("PROVIDER_REFUSED_402")
    with pytest.raises(pipeline.ProviderErrorsPersist, match="402"):
        with limit:
            pass  # no new request after the stop
    release.set()
    first.join()
    assert outcome == ["finished"] and limit.in_flight == 0  # the request already in flight completed
    limit.stop("later reason")
    assert limit.stopped == "PROVIDER_REFUSED_402"


def test_judge_cli_stops_all_workers_on_402(tmp_path, monkeypatch):
    from lecturelens_real_eval.l4 import cli

    calls = []

    class Response:
        status_code = 402

        def json(self):
            return {"error": {"message": "Insufficient Balance"}}

    def post(*args, **kwargs):
        calls.append(1)
        time.sleep(0.05)
        return Response()

    monkeypatch.setattr(cli.httpx, "post", post)
    ledger = make_ledger(tmp_path, stop=10, cap=1)
    limit = pipeline.AdaptiveLimit(6, 4)
    counter = pipeline.InflightCounter(tmp_path / "inflight.json")
    raw = tmp_path / "raw"
    raw.mkdir()
    one = entry()
    errors = []

    def worker():
        try:
            cli.judge_one(one, ledger, "t", "k", raw, limit, counter)
        except pipeline.ProviderErrorsPersist as error:
            errors.append(str(error))

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 12 and len(calls) <= 6  # only the first wave was in flight; nothing after the stop
    assert ledger.summary()["outstanding_nano"] == 0


def test_balance_precheck_converts_cny_and_applies_the_margin():
    payload = {"is_available": True, "balance_infos": [{"currency": "CNY", "total_balance": "136.91"}]}
    usd = pipeline.balance_usd(payload)
    assert usd == pytest.approx(136.91 / 7.3)
    assert pipeline.balance_sufficient(usd, 14.4)  # 18.75 >= 1.2 x 14.4
    assert not pipeline.balance_sufficient(usd, 16.0)
    assert pipeline.balance_usd({"is_available": False, "balance_infos": []}) is None
    assert not pipeline.balance_sufficient(None, 0.1)
    with pytest.raises(ValueError, match="currency"):
        pipeline.balance_usd(
            {"is_available": True, "balance_infos": [{"currency": "EUR", "total_balance": "1"}]}
        )


def test_remaining_spend_counts_unrun_units_and_unjudged_responses():
    nano = pipeline.remaining_spend(
        units_total=864,
        units_done=564,
        product_unit_nano=3_000_000,
        ok_rate=0.9,
        judged=150,
        ok_records=500,
        judge_mean_nano=20_000_000,
    )
    assert nano == 300 * 3_000_000 + (350 + 300 * 0.9) * 20_000_000


def test_rerun_and_rejudge_happen_once_and_are_logged(tmp_path):
    from lecturelens_real_eval.l4 import cli

    rep = tmp_path / "runs/holdout/rep2/rag"
    rep.mkdir(parents=True)
    (rep / "h-x01-01.json").write_text(json.dumps({"status": "failed", "error_code": "HTTP_502"}))
    (rep / "h-x01-03.json").write_text(json.dumps({"status": "ok"}))
    args = [
        "--root",
        str(tmp_path),
        "rerun",
        "--split",
        "holdout",
        "--rep",
        "2",
        "--reason",
        "PROVIDER_BALANCE",
    ]
    cli.main(args + ["--units", "rag:h-x01-01,study:h-x01-02"])
    assert not (rep / "h-x01-01.json").exists()
    assert (tmp_path / "runs/holdout/rep2/superseded/rag/h-x01-01.json").exists()
    log = [json.loads(line) for line in (tmp_path / "runs/holdout/reruns.jsonl").read_text().splitlines()]
    assert [(e["path"], e["superseded_error"]) for e in log] == [("rag", "HTTP_502"), ("study", "NO_RECORD")]
    with pytest.raises(SystemExit, match="already rerun once"):
        cli.main(args + ["--units", "rag:h-x01-01"])
    with pytest.raises(SystemExit, match="only failed units"):
        cli.main(args + ["--units", "rag:h-x01-03"])
    base = tmp_path / "judge/holdout/rep1"
    base.mkdir(parents=True)
    (base / "decisions.json").write_text(
        json.dumps({"r1": {"verdict": "UNDETERMINED"}, "r2": {"verdict": "CORRECT"}})
    )
    (base / "raw").mkdir()
    (base / "raw/r1.1.json").write_text('{"error": "402"}')
    judge_args = ["--root", str(tmp_path), "rejudge", "--split", "holdout", "--label", "rep1"]
    cli.main(judge_args + ["--ids", "r1", "--reason", "PROVIDER_BALANCE"])
    assert set(json.loads((base / "decisions.json").read_text())) == {"r2"}
    assert (base / "raw/superseded/r1.1.json").exists() and not (base / "raw/r1.1.json").exists()
    with pytest.raises(SystemExit, match="already rejudged once"):
        cli.main(judge_args + ["--ids", "r1", "--reason", "PROVIDER_BALANCE"])


def test_merged_packets_keep_colliding_response_ids_apart(tmp_path):
    rep1 = [r for r in responses() if r["rep"] == 1]
    rep2 = [r for r in responses() if r["rep"] == 2]
    write_packet(tmp_path / "rep1", rep1, 1)
    write_packet(tmp_path / "rep2", rep2, 1)  # same seed: the same response ids in both packets
    entries, mapping, decisions = pipeline.merged(tmp_path, ["rep1", "rep2"])
    assert len(entries) == len(mapping) == len(decisions) == 6
    assert {w["rep"] for w in mapping.values()} == {1, 2}
    lectures = {"h-x01-01": "mit-6.034-f10-lec11"}
    out = pipeline.agreement_by_course(entries, mapping, decisions, lectures, seed=3, fraction=1.0)
    review, key = out["6.034"]
    ids = [e["response_id"] for e in review["entries"]]
    assert len(ids) == 6 and all(i.startswith("a") and "/" not in i for i in ids)
    assert sorted(key["source_ids"].values()) == sorted(mapping) and "rep" not in json.dumps(review)
