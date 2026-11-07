"""Seeded stratified blind review; no provider client or automatic human labels."""

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

from dataset import digest, load, write
from scoring import LABELS, agreement, metrics

SEED = 20261107


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def export(runs, output):
    _, groups, _ = load()
    scripts = {d["dialogue_id"]: d for ds in groups.values() for d in ds}
    strata = defaultdict(list)
    for d in scripts.values():
        for ordinal, t in enumerate(d["turns"], 1):
            strata[(d["course_id"], t["category"])].append(f"{d['dialogue_id']}:{ordinal}")
    rng = random.Random(SEED)
    selected, overlap = [], set()
    for stratum in sorted(strata):
        values = sorted(strata[stratum])
        rng.shuffle(values)
        selected.extend(values[:5])
        overlap.add(values[0])
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    assignments, mapping, kinds = {"A": [], "B": []}, {}, set()
    reference_version = None
    for run_index, run in enumerate(runs):
        run = Path(run)
        config = json.loads((run / "config.json").read_text())
        kinds.add(config["data_kind"])
        if config["smoke"]:
            raise ValueError("FULL_RUN_REQUIRED_FOR_FROZEN_SAMPLE")
        if reference_version and reference_version != config["dataset_lock_sha256"]:
            raise ValueError("DATASET_MISMATCH")
        reference_version = config["dataset_lock_sha256"]
        rows = jsonl(run / "turns.jsonl")
        by_key = {r["turn_key"]: r for r in rows}
        expected = {k for keys in strata.values() for k in keys}
        if len(rows) != len(by_key) or set(by_key) != expected:
            raise ValueError("RUN_DOES_NOT_ACCOUNT_FOR_EVERY_SCHEDULED_TURN")
        for key in selected:
            r = by_key[key]
            did, ordinal = key.rsplit(":", 1)
            history = [by_key[f"{did}:{i}"] for i in range(1, int(ordinal))]
            item_id = hashlib.sha256(f"{SEED}:{run_index}:{key}".encode()).hexdigest()[:24]
            packet = dict(
                item_id=item_id,
                learner_text=r["script"]["text"],
                history=[
                    dict(
                        learner=h["script"]["text"],
                        answer=h["answer"],
                        evaluation=h["evaluation"],
                        status=h["status"],
                    )
                    for h in history
                ],
                answer=r["answer"],
                evaluation=r["evaluation"],
                status=r["status"],
                outcome=r["outcome"],
                citations=r["citations"],
                reference=r["script"]["reference"],
            )
            mapping[item_id] = dict(
                run_index=run_index,
                turn_key=key,
                course_id=r["course_id"],
                split=r["split"],
                category=r["script"]["category"],
                model_review=r.get("review"),
                outcome=r["outcome"],
                expected_answer=not r["script"]["expected_insufficient"],
                data_kind=config["data_kind"],
            )
            assignments["A"].append(packet)
            if key in overlap:
                assignments["B"].append(packet)
    if len(kinds) != 1:
        raise ValueError("NEVER_MIX_MOCK_AND_REAL")
    private = dict(
        seed=SEED,
        runs=[
            dict(
                path=str(Path(p).resolve()),
                turns_sha256=digest(Path(p) / "turns.jsonl"),
                config_sha256=digest(Path(p) / "config.json"),
            )
            for p in runs
        ],
        data_kind=kinds.pop(),
        mappings=mapping,
        packets={},
    )
    for rater, items in assignments.items():
        random.Random(SEED + ord(rater)).shuffle(items)
        packet = dict(
            data_kind=private["data_kind"],
            rater=rater,
            instruction="Independent annotation; do not share answers or identities before both submissions. "
            "Segment ALL substantive assertions in answer and evaluation. Reference facts may "
            "support arithmetic derivations; never infer missing parameters. No model quality "
            "inference is permitted from MOCK packets.",
            items=items,
        )
        path = out / f"packet-{rater}.json"
        write(path, packet)
        private["packets"][rater] = digest(path)
        write(
            out / f"annotation-{rater}.json",
            dict(
                packet_sha256=digest(path),
                rater=rater,
                ratings=[
                    dict(
                        item_id=i["item_id"],
                        complete=False,
                        overall_supported=None,
                        context_consistent=None,
                        abstention_correct=None,
                        claims=[],
                        citation_checks=[],
                        reason="",
                    )
                    for i in items
                ],
            ),
        )
    write(out / "private-key.json", private)
    (out / "private-key.json").chmod(0o600)
    return dict(
        sampled_turns_per_run=len(selected),
        overlap_per_run=len(overlap),
        assignments={k: len(v) for k, v in assignments.items()},
        human_scores_status="NOT_RUN",
    )


def validate_rating(r, item):
    if type(r["complete"]) is not bool:
        raise ValueError("COMPLETE_MUST_BE_BOOLEAN")
    if not r["complete"]:
        if r["claims"] or r["citation_checks"] or r["overall_supported"] is not None:
            raise ValueError("PARTIAL_RATING_MUST_REMAIN_MISSING")
        return
    if r["overall_supported"] not in LABELS or not r["reason"].strip():
        raise ValueError("LABEL_AND_REASON_REQUIRED")
    for field in ("context_consistent", "abstention_correct"):
        if r[field] not in (True, False, None):
            raise ValueError("INVALID_AUXILIARY_LABEL")
    claims = {c["claim_id"]: c for c in r["claims"]}
    if len(claims) != len(r["claims"]):
        raise ValueError("DUPLICATE_CLAIM")
    citations = {e["evidence_id"]: e["text"] for e in item["citations"]}
    all_text = (item["answer"] or "") + "\n" + (item["evaluation"] or "")
    for c in claims.values():
        if not c["text"].strip() or c["text"] not in all_text or type(c["requires_citation"]) is not bool:
            raise ValueError("CLAIM_MUST_BE_EXACT_ANSWER_SPAN")
        if (
            len(set(c["citation_ids"])) != len(c["citation_ids"])
            or not set(c["citation_ids"]) <= citations.keys()
        ):
            raise ValueError("UNKNOWN_OR_DUPLICATE_CITATION")
    expected = {(c["claim_id"], eid) for c in claims.values() for eid in c["citation_ids"]}
    checks = {(c["claim_id"], c["evidence_id"]) for c in r["citation_checks"]}
    if checks != expected or len(checks) != len(r["citation_checks"]):
        raise ValueError("MISSING_OR_DUPLICATE_PAIR_JUDGMENT")
    if set(citations) != {eid for _, eid in checks}:
        raise ValueError("EVERY_OUTPUT_CITATION_REQUIRES_AUDIT")
    for c in r["citation_checks"]:
        if c["label"] not in LABELS:
            raise ValueError("INVALID_PAIR_LABEL")
        if c["label"] == "supported" and (
            not c["quote"].strip() or c["quote"] not in citations[c["evidence_id"]]
        ):
            raise ValueError("SUPPORT_REQUIRES_EXACT_SOURCE_QUOTE")
    if item["outcome"] in ("answered", "socratic_prompt") and not claims:
        raise ValueError("ANSWER_REQUIRES_CLAIM_INVENTORY")


def import_annotations(key_path, packet_path, rating_path, output):
    key, packet, ratings = [json.loads(Path(p).read_text()) for p in (key_path, packet_path, rating_path)]
    rater = packet["rater"]
    if (
        ratings["rater"] != rater
        or digest(packet_path) != key["packets"][rater]
        or ratings["packet_sha256"] != digest(packet_path)
    ):
        raise ValueError("PACKET_BINDING_FAILED")
    items = {i["item_id"]: i for i in packet["items"]}
    rows = {r["item_id"]: r for r in ratings["ratings"]}
    if len(rows) != len(ratings["ratings"]) or rows.keys() != items.keys():
        raise ValueError("ALL_ASSIGNED_UNITS_REQUIRED_NO_DUPLICATES")
    for item_id, r in rows.items():
        validate_rating(r, items[item_id])
    write(
        output,
        dict(
            rater=rater,
            key_sha256=digest(key_path),
            data_kind=key["data_kind"],
            packet_sha256=digest(packet_path),
            ratings=list(rows.values()),
        ),
    )
    return dict(imported=len(rows), completed=sum(bool(r["complete"]) for r in rows.values()))


def score(key_path, imports, output):
    key = json.loads(Path(key_path).read_text())
    raters, by_rater = {}, {}
    for path in imports:
        data = json.loads(Path(path).read_text())
        if data["key_sha256"] != digest(key_path) or data["rater"] in raters:
            raise ValueError("KEY_MISMATCH_OR_DUPLICATE_RATER")
        name = data["rater"]
        rows = data["ratings"]
        raters[name] = metrics(rows)
        by_rater[name] = {r["item_id"]: r for r in rows}
    a, b = by_rater.get("A", {}), by_rater.get("B", {})
    inter = [
        (
            a.get(i, {}).get("overall_supported") if a.get(i, {}).get("complete") else None,
            r.get("overall_supported") if r["complete"] else None,
        )
        for i, r in b.items()
        if key["mappings"][i]["expected_answer"]
    ]
    model_pairs = []
    for i, r in a.items():
        meta = key["mappings"][i]
        # Support judgment is inapplicable to abstention. Keep all eligible assigned answers,
        # including failed/unannotated judgments, in the reported eligible count.
        if not meta["expected_answer"]:
            continue
        judged = (meta.get("model_review") or {}).get("answer_supported")
        model = "supported" if judged is True else "unsupported" if judged is False else None
        human = r["overall_supported"] if r["complete"] else None
        model_pairs.append((model, human))
    result = dict(
        data_kind=key["data_kind"],
        raters=raters,
        quality_status=(
            "NOT_RUN"
            if not any(r["annotated_turns"] for r in raters.values())
            else "MOCK_NOT_QUALITY"
            if key["data_kind"] == "MOCK"
            else "HUMAN_ANNOTATED_SUBSET_ONLY"
        ),
        model_human_agreement=agreement(model_pairs),
        double_annotation_agreement=agreement(inter),
        human_scores_status="ANNOTATED" if any(r["annotated_turns"] for r in raters.values()) else "NOT_RUN",
        note="No population claim or real quality inference from synthetic/mock labels. "
        "Annotator A is preregistered primary; B is independent overlap, never pooled to inflate n.",
    )
    write(output, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    e = sub.add_parser("export")
    e.add_argument("--runs", nargs="+", required=True)
    e.add_argument("--output", required=True)
    i = sub.add_parser("import")
    i.add_argument("--key", required=True)
    i.add_argument("--packet", required=True)
    i.add_argument("--ratings", required=True)
    i.add_argument("--output", required=True)
    s = sub.add_parser("score")
    s.add_argument("--key", required=True)
    s.add_argument("--imports", nargs="+", required=True)
    s.add_argument("--output", required=True)
    a = p.parse_args()
    result = (
        export(a.runs, a.output)
        if a.command == "export"
        else import_annotations(a.key, a.packet, a.ratings, a.output)
        if a.command == "import"
        else score(a.key, a.imports, a.output)
    )
    print(json.dumps(result))
