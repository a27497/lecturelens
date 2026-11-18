"""Offline checks for the L4 benchmark harness: no network, no provider, synthetic data only."""

import json
import multiprocessing
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from lecturelens_real_eval.l4 import blind, citations, judge, pricing, questions, scoring
from lecturelens_real_eval.l4.ledger import BudgetExceeded, Ledger, LedgerError
from lecturelens_real_eval.l4.normalize import normalize
from lecturelens_real_eval.l4.runner import L4TutorStore

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

CAPTIONS = """[00:09-00:40] So this kind of tree is called an
[00:40-01:14] identification tree. But a decision tree is a label for something else.
[01:20-01:50] Some characteristics don't matter, and some -- matter only part of the time.
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
    assert (
        ok(cue("01:20", "01:50", "some characteristics DON'T matter, and some matter only"), windows) is None
    )
    assert ok(cue("01:20", "01:50", "matter only some part"), windows) == "quote not in the cited windows"
    # A quote across a window boundary must name both windows ...
    spanning = "called an identification tree"
    assert ok(cue("00:40", "01:14", spanning), windows) == "quote not in the cited windows"
    assert ok(cue("00:09", "01:14", spanning), windows) is None
    # ... and a cue may not be wider than its quote (one window off is an error, not a tolerance).
    assert ok(cue("00:09", "01:14", "a decision tree is a label"), windows) == "cue wider than the quote"
    assert ok(cue("00:40", "01:50", "a decision tree is a label"), windows) == "cue wider than the quote"
    # Labels must be real window boundaries.
    assert "not a window start" in ok(cue("00:10", "00:40", "this kind of tree"), windows)
    assert "not a window end" in ok(cue("00:40", "01:20", "identification tree"), windows)
    assert ok(cue("00:09", "00:40", " -- "), windows) == "empty quote"


def test_citation_locate_and_item_errors():
    windows = citations.parse_windows(CAPTIONS)
    assert citations.locate("called an identification tree", windows) == [("00:09", "01:14")]
    assert citations.locate("decision tree", windows) == [("00:40", "01:14")]
    item = {
        "item_id": "h-x01-01",
        "lecture_id": "lec",
        "nuggets": [
            {"id": "N1", "cues": [cue("00:40", "01:14", "identification tree")]},
            {"id": "N2", "cues": [cue("00:40", "01:14", "called an identification tree")]},
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
    assert body["max_tokens"] == judge.MAX_TOKENS
    assert '"rag"' not in body["messages"][1]["content"]
    assert judge.reservation_nano(body) == pricing.upper_nano(
        "deepseek-v4-pro", len(blind.canonical(body)), 8192
    )


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


def test_product_tutor_code_is_unchanged_by_the_harness():
    """The adapter subclasses product classes; the pinned Tutor build stays the PLAN's baseline digest."""
    from lecturelens_real_eval.tutor.flash_ledger import build_digest

    assert build_digest() == "4fcf204f5aed4cb3046f340105083d008dc916829f155877ed834d344971ecaf"
