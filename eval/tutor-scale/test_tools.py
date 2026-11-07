"""Mechanism tests; every scoring label below is hand-constructed, not a human trial."""

import copy
import json

import pytest
from blind import export, import_annotations, score, validate_rating
from dataset import load, write
from scoring import agreement, metrics


def test_frozen_dataset_counts_and_content():
    snapshot, groups, counts = load()
    assert counts == {
        "development": {"courses": 3, "sessions": 48, "turns": 240},
        "holdout": {"courses": 1, "sessions": 16, "turns": 80},
    }
    assert len({e["text"] for lecture in snapshot["lectures"].values() for e in lecture["evidence"]}) == 64
    assert {t["category"] for ds in groups.values() for d in ds for t in d["turns"]} == {
        "fact",
        "followup",
        "false_premise",
        "insufficient",
        "out_of_scope",
    }


def test_hand_scored_accuracy_coverage_and_missing():
    rows = [
        dict(
            complete=True,
            claims=[
                dict(claim_id="a", requires_citation=True, citation_ids=["e1", "e2"]),
                dict(claim_id="b", requires_citation=True, citation_ids=[]),
                dict(claim_id="c", requires_citation=True, citation_ids=["e3"]),
            ],
            citation_checks=[
                dict(claim_id="a", label="supported"),
                dict(claim_id="a", label="unsupported"),
                dict(claim_id="c", label="uncertain"),
            ],
        ),
        dict(complete=False),
    ]
    m = metrics(rows)
    assert m["citation_support_accuracy"]["value"] == 1 / 3
    assert m["citation_presence_coverage"]["value"] == 2 / 3
    assert m["supported_citation_coverage"]["value"] == 1 / 3
    assert m["missing_turns"] == 1 and m["uncertain_citation_pairs"] == 1
    assert metrics([dict(complete=False)])["status"] == "NOT_RUN"
    assert metrics([])["citation_support_accuracy"]["value"] is None


def test_hand_scored_agreement_kappa():
    pairs = [
        ("supported", "supported"),
        ("supported", "unsupported"),
        ("unsupported", "unsupported"),
        ("unsupported", "unsupported"),
        (None, "supported"),
        ("uncertain", "supported"),
    ]
    a = agreement(pairs)
    assert a["agreement"] == 0.75 and a["cohen_kappa"] == 0.5
    assert a["comparable"] == 4 and a["excluded"] == 2
    assert agreement([("supported", "supported")])["cohen_kappa"] is None
    assert agreement([])["reason"] == "NO_BINARY_PAIRS"


def test_reconcile_missing_and_duplicates():
    from run import reconcile

    scripts = [
        dict(
            dialogue_id="x",
            course_id="energy",
            turns=[dict(text="one"), dict(text="two")],
        )
    ]
    rows = reconcile(scripts, [dict(turn_key="x:1", status="failed")])
    assert [r["status"] for r in rows] == ["failed", "MISSING"]
    with pytest.raises(ValueError, match="DUPLICATE"):
        reconcile(scripts, [dict(turn_key="x:1")] * 2)


def test_live_gates_and_frozen_pins(monkeypatch):
    from run import preflight

    monkeypatch.delenv("LECTURELENS_REAL_EVAL", raising=False)
    with pytest.raises(ValueError, match="OPT_IN"):
        preflight(True, None)
    monkeypatch.setenv("LECTURELENS_REAL_EVAL", "1")
    with pytest.raises(ValueError, match="OPT_IN"):
        preflight(True, None)
    assert preflight(False, None)["data_kind"] == "SYNTHETIC_EVAL_ASSETS"


def fake_run(path, kind="MOCK"):
    _, groups, _ = load()
    path.mkdir()
    write(
        path / "config.json",
        dict(data_kind=kind, smoke=False, dataset_lock_sha256="same"),
    )
    with (path / "turns.jsonl").open("w") as f:
        for ds in groups.values():
            for d in ds:
                for n, t in enumerate(d["turns"], 1):
                    f.write(
                        json.dumps(
                            dict(
                                turn_key=f"{d['dialogue_id']}:{n}",
                                dialogue_id=d["dialogue_id"],
                                course_id=d["course_id"],
                                split="holdout" if d["course_id"] == "energy" else "development",
                                script=t,
                                answer="A synthetic claim.",
                                evaluation="",
                                status="completed",
                                outcome="answered",
                                citations=[],
                                review=dict(answer_supported=True),
                            )
                        )
                        + "\n"
                    )


def test_blind_roundtrip_unannotated_and_binding(tmp_path):
    fake_run(tmp_path / "run")
    stats = export([tmp_path / "run"], tmp_path / "blind")
    assert stats["assignments"] == {"A": 100, "B": 20}
    key = tmp_path / "blind/private-key.json"
    for r in "AB":
        root = tmp_path / "blind"
        result = import_annotations(
            key,
            root / f"packet-{r}.json",
            root / f"annotation-{r}.json",
            root / f"import-{r}.json",
        )
        assert result["completed"] == 0
    result = score(key, [root / "import-A.json", root / "import-B.json"], root / "score.json")
    assert result["human_scores_status"] == "NOT_RUN"
    assert result["model_human_agreement"]["comparable"] == 0
    packet = json.loads((root / "packet-A.json").read_text())
    serialized = json.dumps(packet)
    assert "requested_model" not in serialized and "model_review" not in serialized
    assert "code_sha" not in serialized and "candidate_sha" not in serialized
    assert len({i["item_id"] for i in packet["items"]}) == 100
    ratings = json.loads((root / "annotation-A.json").read_text())
    ratings["ratings"].pop()
    write(root / "missing.json", ratings)
    with pytest.raises(ValueError, match="ALL_ASSIGNED"):
        import_annotations(key, root / "packet-A.json", root / "missing.json", root / "bad.json")
    packet["items"][0]["answer"] = "tampered"
    write(root / "tampered.json", packet)
    with pytest.raises(ValueError, match="BINDING"):
        import_annotations(key, root / "tampered.json", root / "annotation-A.json", root / "bad.json")


def test_mixed_mock_real_refused(tmp_path):
    fake_run(tmp_path / "mock")
    fake_run(tmp_path / "real", "REAL")
    with pytest.raises(ValueError, match="NEVER_MIX"):
        export([tmp_path / "mock", tmp_path / "real"], tmp_path / "blind")


def test_annotation_requires_exact_claim_quote_and_pair():
    item = dict(
        answer="A source claim.",
        evaluation="",
        outcome="answered",
        citations=[dict(evidence_id="e1", text="Reference text.")],
    )
    rating = dict(
        complete=True,
        overall_supported="supported",
        reason="Synthetic label",
        context_consistent=True,
        abstention_correct=None,
        claims=[
            dict(
                claim_id="c1",
                text="A source claim.",
                requires_citation=True,
                citation_ids=["e1"],
            )
        ],
        citation_checks=[
            dict(
                claim_id="c1",
                evidence_id="e1",
                label="supported",
                quote="Reference text.",
            )
        ],
    )
    validate_rating(rating, item)
    changed = copy.deepcopy(rating)
    changed["citation_checks"][0]["quote"] = "invented"
    with pytest.raises(ValueError, match="EXACT_SOURCE"):
        validate_rating(changed, item)
    changed = copy.deepcopy(rating)
    changed["citation_checks"] = []
    with pytest.raises(ValueError, match="PAIR_JUDGMENT"):
        validate_rating(changed, item)


def test_hand_annotation_import_and_score(tmp_path):
    fake_run(tmp_path / "run")
    export([tmp_path / "run"], tmp_path / "blind")
    root = tmp_path / "blind"
    ratings = json.loads((root / "annotation-A.json").read_text())
    key = json.loads((root / "private-key.json").read_text())
    first = next(r for r in ratings["ratings"] if key["mappings"][r["item_id"]]["expected_answer"])
    first.update(
        complete=True,
        overall_supported="unsupported",
        reason="HAND_CONSTRUCTED_EXAMPLE_ONLY",
        claims=[dict(claim_id="c1", text="A synthetic claim.", requires_citation=True, citation_ids=[])],
    )
    write(root / "hand-example.json", ratings)
    imported = import_annotations(
        root / "private-key.json", root / "packet-A.json", root / "hand-example.json", root / "import-A.json"
    )
    assert imported["completed"] == 1
    result = score(root / "private-key.json", [root / "import-A.json"], root / "score.json")
    assert result["raters"]["A"]["supported_citation_coverage"]["denominator"] == 1
    assert result["raters"]["A"]["supported_citation_coverage"]["value"] == 0
    assert result["model_human_agreement"]["comparable"] == 1
    assert result["model_human_agreement"]["agreement"] == 0
    assert result["raters"]["A"]["missing_turns"] == 99


def test_bounded_metadata_tee():
    import httpx
    from run import MetadataTransport

    transport = MetadataTransport(
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"model": "MOCK-v1", "system_fingerprint": "mock-build"})
        )
    )
    with httpx.Client(transport=transport) as client:
        assert client.get("https://unused.invalid").json()["model"] == "MOCK-v1"
    assert transport.metadata == dict(returned_model_version="MOCK-v1", system_fingerprint="mock-build")


def test_failure_accounting_includes_failed_shards_and_unknowns():
    from run import accounting_totals

    result = accounting_totals([dict(calls=3, pending=1), dict(calls=1, pending=0)])
    assert result["reserved_calls"] == 4 and result["settled_calls"] == 3
    assert result["pending_calls"] == 1
    result = accounting_totals([dict(calls=2, pending=0), None])
    assert result["settled_calls"] is None and result["unknown_accounting_shards"] == 1
    assert result["known_accounting"]["settled_calls"] == 2
