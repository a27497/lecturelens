"""Pilot census review, separate from v1's unchanged random 100/20 sample."""

import argparse
import json
import random
from pathlib import Path

from records import read_run
from shared import digest, object_hash, read, validate_citations, write
from task_scores import summarize

FIELDS = ("task_correct", "abstention_correct", "context_consistent")


def export(queue_path, run_path, output):
    run = read_run(queue_path, run_path)
    if not run["config"] or not (Path(run_path) / "expected-turns.json").exists():
        raise ValueError("REVIEW_REQUIRES_BOUND_RUN_METADATA")
    rows = run["rows"]
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    mappings = {}
    items = []
    for r in rows:
        item_id = object_hash(
            ["pilot-census-v2", run["queue_sha256"], str(Path(run_path).resolve()), r["turn_key"]]
        )[:24]
        mappings[item_id] = r["turn_key"]
        items.append(
            dict(
                item_id=item_id,
                learner_text=r["script"]["text"],
                status=r["status"],
                outcome=r["outcome"],
                answer=r["answer"],
                evaluation=r["evaluation"],
                citations=r["citations"],
                reference=r["script"]["reference"],
                context_followup=r["script"]["context_followup"],
                history=[
                    dict(
                        learner_text=h["script"]["text"],
                        answer=h["answer"],
                        evaluation=h["evaluation"],
                        outcome=h["outcome"],
                        status=h["status"],
                    )
                    for h in rows
                    if h["dialogue_id"] == r["dialogue_id"] and h["ordinal"] < r["ordinal"]
                ],
            )
        )
    key = dict(
        schema="pilot-census-v2",
        queue_sha256=run["queue_sha256"],
        run_path=run["directory"],
        input_hashes=run["input_hashes"],
        mappings=mappings,
        packets={},
    )
    overlap = set(run["queue"]["review_overlap_turns"])
    for rater in ("A", "B"):
        selected = items.copy() if rater == "A" else [i for i in items if mappings[i["item_id"]] in overlap]
        random.Random(20261108 + ord(rater)).shuffle(selected)
        packet = dict(
            design="FROZEN_PILOT_CENSUS_NOT_ORIGINAL_RANDOM_SAMPLE",
            rater=rater,
            data_kind=run["config"]["data_kind"],
            instructions="Independent review. Use all prior conversation, evidence conditions and reference "
            "rubric. Cross-turn consistency concerns referents, conditions and evidence, never string equality. "
            "A failed prior answer cannot establish an antecedent; clarification or clean abstention may be "
            "context-consistent while task appropriateness is judged separately. Do not share labels.",
            items=selected,
        )
        path = out / f"packet-{rater}.json"
        write(path, packet)
        key["packets"][rater] = digest(path)
        write(
            out / f"annotation-{rater}.json",
            dict(
                packet_sha256=digest(path),
                rater=rater,
                annotation_source="UNANNOTATED",
                ratings=[
                    dict(
                        item_id=i["item_id"],
                        complete=False,
                        overall_supported=None,
                        task_correct=None,
                        abstention_correct=None,
                        context_consistent=None,
                        claims=[],
                        citation_checks=[],
                        reason="",
                    )
                    for i in selected
                ],
            ),
        )
    write(out / "private-key.json", key)
    (out / "private-key.json").chmod(0o600)
    return dict(
        primary=len(items), overlap=len(overlap), design="PILOT_CENSUS", human_scores_status="NOT_RUN"
    )


def validate(r, item):
    for f in FIELDS:
        if r.get(f) is not None and type(r[f]) is not bool:
            raise ValueError("TASK_JUDGMENT_MUST_BE_BOOLEAN_OR_NULL")
    if not r["complete"] and any(r.get(f) is not None for f in FIELDS):
        raise ValueError("INCOMPLETE_ANNOTATION_HAS_JUDGMENTS")
    if r["complete"] and item["status"] != "completed":
        raise ValueError("EXECUTION_FAILURE_IS_NOT_A_SEMANTIC_ANNOTATION")
    validate_citations(r, item)


def bound_ratings(key, packet, ratings, packet_path):
    rater = packet["rater"]
    if (
        rater not in key["packets"]
        or ratings["rater"] != rater
        or digest(packet_path) != key["packets"][rater]
        or ratings["packet_sha256"] != digest(packet_path)
    ):
        raise ValueError("REVIEW_PACKET_BINDING_FAILED")
    items = {i["item_id"]: i for i in packet["items"]}
    by_id = {r["item_id"]: r for r in ratings["ratings"]}
    if len(by_id) != len(ratings["ratings"]) or by_id.keys() != items.keys():
        raise ValueError("ALL_ASSIGNED_UNITS_REQUIRED_NO_DUPLICATES")
    source = ratings["annotation_source"]
    if source not in ("HUMAN", "HAND_CONSTRUCTED_FIXTURE", "UNANNOTATED") or (
        source == "UNANNOTATED" and any(r["complete"] for r in by_id.values())
    ):
        raise ValueError("VALID_ANNOTATION_SOURCE_REQUIRED")
    for item_id, r in by_id.items():
        validate(r, items[item_id])
    return by_id


def import_annotations(key_path, packet_path, ratings_path, output):
    key, packet, ratings = read(key_path), read(packet_path), read(ratings_path)
    by_id = bound_ratings(key, packet, ratings, packet_path)
    write(
        output,
        dict(
            schema="pilot-census-import-v2",
            rater=packet["rater"],
            key_sha256=digest(key_path),
            packet_path=str(Path(packet_path).resolve()),
            packet_sha256=digest(packet_path),
            annotation_source=ratings["annotation_source"],
            ratings=list(by_id.values()),
        ),
    )
    return dict(assigned=len(by_id), complete=sum(r["complete"] for r in by_id.values()))


def score(queue_path, key_path, imports, output):
    key = read(key_path)
    run = read_run(queue_path, key["run_path"])
    if key["queue_sha256"] != run["queue_sha256"] or key["input_hashes"] != run["input_hashes"]:
        raise ValueError("REVIEW_SOURCE_RUN_CHANGED")
    raters = {}
    sources = {}
    for path in imports:
        imported = read(path)
        name = imported["rater"]
        if name in raters or imported["key_sha256"] != digest(key_path):
            raise ValueError("DUPLICATE_RATER_OR_KEY_MISMATCH")
        packet_path = imported["packet_path"]
        packet = read(packet_path)
        values = bound_ratings(key, packet, imported, packet_path)
        raters[name] = {key["mappings"][i]: r for i, r in values.items()}
        sources[name] = imported["annotation_source"]
    result = summarize(run, raters.get("A", {}), raters.get("B", {}))
    # Agreement with a real model must also have actual human labels, not fixture/other-model labels.
    if sources.get("A") != "HUMAN":
        from shared import agreement

        result["model_human_support_agreement"] = agreement(
            [(None, None) for r in run["rows"] if not r["script"]["expected_insufficient"]]
        )
    if sources.get("A") != "HUMAN" or sources.get("B") != "HUMAN":
        from shared import agreement

        result["independent_human_overlap_support_agreement"] = agreement(
            [
                (None, None)
                for r in run["rows"]
                if r["turn_key"] in raters.get("B", {}) and not r["script"]["expected_insufficient"]
            ]
        )
    for field in ("model_human_support_agreement", "independent_human_overlap_support_agreement"):
        result[field]["status"] = "PAIRED_SAMPLE_ONLY" if result[field]["comparable"] else "NOT_RUN"
    result.update(
        review_design="PILOT_CENSUS",
        annotation_sources=sources,
        queue_sha256=run["queue_sha256"],
        input_hashes=run["input_hashes"],
        human_scores_status="ANNOTATED_SUBSET"
        if sources.get("A") == "HUMAN" and result["execution"]["annotated_inventory_turns"]
        else "NOT_RUN",
    )
    write(output, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    e = sub.add_parser("export")
    e.add_argument("--queue", required=True)
    e.add_argument("--run", required=True)
    e.add_argument("--output", required=True)
    i = sub.add_parser("import")
    i.add_argument("--key", required=True)
    i.add_argument("--packet", required=True)
    i.add_argument("--ratings", required=True)
    i.add_argument("--output", required=True)
    s = sub.add_parser("score")
    s.add_argument("--queue", required=True)
    s.add_argument("--key", required=True)
    s.add_argument("--imports", nargs="+", required=True)
    s.add_argument("--output", required=True)
    a = p.parse_args()
    result = (
        export(a.queue, a.run, a.output)
        if a.command == "export"
        else import_annotations(a.key, a.packet, a.ratings, a.output)
        if a.command == "import"
        else score(a.queue, a.key, a.imports, a.output)
    )
    print(json.dumps(result))
