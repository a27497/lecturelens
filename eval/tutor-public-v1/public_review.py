"""Public-set census export using existing v2 annotation validation and scoring."""

import argparse
import json
import random
from pathlib import Path

from public_bridge import bound_ratings, import_annotations, summarize
from public_dataset import HERE, digest, expected_rows, object_hash, read, select, write
from public_mock import reconcile


def read_run(directory):
    directory = Path(directory)
    config = read(directory / "config.json")
    snapshot, scripts = select(
        config["scope"], sessions=config["selected_dialogue_ids"], allow_holdout=True
    )
    planned = expected_rows(snapshot, scripts)
    if (
        config["data_kind"] != "MOCK"
        or config["live"] is not False
        or config["dataset_lock_sha256"] != digest(HERE / "dataset-lock.json")
        or config["expected_turns_sha256"] != object_hash(planned)
        or read(directory / "expected-turns.json")
        != {"dataset_lock_sha256": config["dataset_lock_sha256"], "turns": planned}
    ):
        raise ValueError("PUBLIC_RUN_BINDING_CHANGED")
    raw = [
        json.loads(line)
        for line in (directory / "turns.jsonl").read_text().splitlines()
    ]
    rows = reconcile(planned, raw)
    by_plan = {r["turn_key"]: r for r in planned}
    for row in raw:
        if any(row[k] != v for k, v in by_plan[row["turn_key"]].items()):
            raise ValueError("RESULT_SCOPE_OR_SCRIPT_CHANGED")
    return {
        "rows": rows,
        "planned": planned,
        "config": config,
        "scripts": scripts,
        "directory": str(directory.resolve()),
        "input_hashes": {
            str(p.relative_to(directory)): digest(p)
            for p in sorted(directory.rglob("*.json*"))
            if p.name
            in (
                "config.json",
                "expected-turns.json",
                "turns.jsonl",
                "calls.jsonl",
                "ledger.jsonl",
                "accounting.json",
                "summary.json",
            )
        },
    }


def export(directory, output):
    run = read_run(directory)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    mappings, items = {}, []
    for row in run["rows"]:
        item_id = object_hash(
            [
                "public-census-v1",
                run["config"]["dataset_lock_sha256"],
                run["directory"],
                row["turn_key"],
            ]
        )[:24]
        mappings[item_id] = row["turn_key"]
        # System identities and model-review labels never enter reviewer packets.
        items.append(
            {
                "item_id": item_id,
                "learner_text": row["script"]["text"],
                "status": row["status"],
                "outcome": row["outcome"],
                "answer": row["answer"],
                "evaluation": row["evaluation"],
                "citations": row["citations"],
                "reference": row["script"]["reference"],
                "context_followup": row["script"]["context_followup"],
                "history": [
                    {
                        "learner_text": h["script"]["text"],
                        "answer": h["answer"],
                        "evaluation": h["evaluation"],
                        "status": h["status"],
                        "outcome": h["outcome"],
                    }
                    for h in run["rows"]
                    if h["dialogue_id"] == row["dialogue_id"]
                    and h["ordinal"] < row["ordinal"]
                ],
            }
        )
    key = {
        "schema": "public-course-census-v1",
        "run_path": run["directory"],
        "input_hashes": run["input_hashes"],
        "dataset_lock_sha256": run["config"]["dataset_lock_sha256"],
        "mappings": mappings,
        "packets": {},
    }
    # Preregistered one context-bearing turn (ordinal 2) per selected session.
    overlap = {f"{d['dialogue_id']}:2" for d in run["scripts"]}
    for rater in ("A", "B"):
        selected = (
            items.copy()
            if rater == "A"
            else [i for i in items if mappings[i["item_id"]] in overlap]
        )
        random.Random(20261109 + ord(rater)).shuffle(selected)
        packet = {
            "rater": rater,
            "data_kind": "MOCK",
            "design": "PUBLIC_SET_CENSUS_NOT_OLD_RANDOM_SAMPLE",
            "source_attributions": [
                s
                for s in read(HERE / "sources.json")["sources"]
                if s["course_id"] in {d["course_id"] for d in run["scripts"]}
            ],
            "instructions": "Independent annotation. Use source quotes and all prior turns. "
            "Judge semantic conditions/referents, never string equality. Do not share labels. "
            "Codex references are provisional, not independent expert gold.",
            "items": selected,
        }
        path = out / f"packet-{rater}.json"
        write(path, packet)
        key["packets"][rater] = digest(path)
        write(
            out / f"annotation-{rater}.json",
            {
                "packet_sha256": digest(path),
                "rater": rater,
                "annotation_source": "UNANNOTATED",
                "ratings": [
                    {
                        "item_id": i["item_id"],
                        "complete": False,
                        "overall_supported": None,
                        "task_correct": None,
                        "abstention_correct": None,
                        "context_consistent": None,
                        "claims": [],
                        "citation_checks": [],
                        "reason": "",
                    }
                    for i in selected
                ],
            },
        )
    write(out / "private-key.json", key)
    (out / "private-key.json").chmod(0o600)
    return {
        "primary": len(items),
        "independent_overlap": len(overlap),
        "human_scores_status": "NOT_RUN",
    }


def score(key_path, imports, output):
    key = read(key_path)
    run = read_run(key["run_path"])
    if (
        key["input_hashes"] != run["input_hashes"]
        or key["dataset_lock_sha256"] != run["config"]["dataset_lock_sha256"]
    ):
        raise ValueError("SOURCE_RUN_CHANGED_AFTER_EXPORT")
    raters, sources = {}, {}
    for path in imports:
        imported = read(path)
        name = imported["rater"]
        if name in raters or imported["key_sha256"] != digest(key_path):
            raise ValueError("DUPLICATE_RATER_OR_KEY_MISMATCH")
        packet_path = imported["packet_path"]
        values = bound_ratings(key, read(packet_path), imported, packet_path)
        raters[name] = {key["mappings"][k]: v for k, v in values.items()}
        sources[name] = imported["annotation_source"]
    # No annotated Mock labels are promoted to real task or agreement metrics.
    result = summarize(
        run,
        raters.get("A", {}),
        raters.get("B", {}) if sources.get("A") == sources.get("B") == "HUMAN" else {},
    )
    result.update(
        annotation_sources=sources,
        human_scores_status="NOT_RUN",
        real_quality_status="NOT_RUN",
        review_design="PUBLIC_SET_CENSUS_NOT_OLD_RANDOM_SAMPLE",
    )
    write(output, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    e = sub.add_parser("export")
    e.add_argument("--run", required=True)
    e.add_argument("--output", required=True)
    i = sub.add_parser("import")
    for key in ("key", "packet", "ratings", "output"):
        i.add_argument("--" + key, required=True)
    s = sub.add_parser("score")
    s.add_argument("--key", required=True)
    s.add_argument("--imports", nargs="+", required=True)
    s.add_argument("--output", required=True)
    a = p.parse_args()
    if a.command == "export":
        result = export(a.run, a.output)
    elif a.command == "import":
        result = import_annotations(a.key, a.packet, a.ratings, a.output)
    else:
        result = score(a.key, a.imports, a.output)
    print(json.dumps(result))
