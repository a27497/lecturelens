"""Offline public-course projection and frozen-contract validation."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from author_public import SESSIONS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VERSION = "tutor-public-v1"
SPLIT_SHA = "1eea49193925d5565bae62ce611d79871a1b78ad450c494b344ac4456bed9a3c"


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def write(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def project():
    if digest(HERE / "course-split.json") != SPLIT_SHA:
        raise ValueError("PREREGISTERED_COURSE_SPLIT_CHANGED")
    split = read(HERE / "course-split.json")
    sources = read(HERE / "sources.json")["sources"]
    snapshot = {
        "material_kind": "PUBLIC_COURSE_TEXT",
        "version": VERSION,
        "lectures": {},
    }
    groups = {"development": [], "holdout": []}
    for course, src in zip(split["courses"], sources, strict=True):
        for field in ("course_id", "split", "dialogue_ids", "unit_url", "source_path"):
            if course[field] != src[field]:
                raise ValueError("SOURCE_SPLIT_MISMATCH")
        for path, sha in (
            (src["local_path"], src["sha256"]),
            (src["license_local_path"], src["license_sha256"]),
        ):
            if digest(HERE / path) != sha:
                raise ValueError("SOURCE_HASH_MISMATCH")
        lines = (HERE / src["local_path"]).read_text().splitlines(keepends=True)
        evidence = []
        # Blank-separated blocks preserve exact source bytes and line locators.
        for match in re.finditer(r"\S[^\n]*(?:\n(?!\s*\n)[^\n]*)*", "".join(lines)):
            text = match.group().rstrip("\n")
            lo = "".join(lines)[: match.start()].count("\n") + 1
            hi = lo + text.count("\n")
            if lo <= 5 or not text.strip(": \n") or text.lstrip().startswith("![]("):
                continue
            if len(text) > 8000:
                raise ValueError("SOURCE_BLOCK_TOO_LONG")
            eid = object_hash([src["sha256"], lo, hi, text])
            evidence.append(
                {
                    "evidence_id": eid,
                    "text": text,
                    "start_ms": 0,
                    "end_ms": 0,
                    "source_type": "DOCUMENT_PAGE",
                    "course": course["course_id"],
                    "line_start": lo,
                    "line_end": hi,
                    "source_path": src["local_path"],
                    "source_url": f"{src['repository_source_url']}#L{lo}-L{hi}",
                    "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                    "locator_note": "Original Markdown lines; 0/0 are required legacy placeholders, NOT timestamps or page numbers.",
                }
            )
        snapshot["lectures"][course["course_id"]] = {
            "course": course["course_id"],
            "title": course["title"],
            "split": course["split"],
            "attribution": src["attribution"],
            "evidence": evidence,
        }
        for did in course["dialogue_ids"]:
            turns = []
            for n, (
                question,
                kind,
                ranges,
                points,
                boundary,
                gap,
                depends,
            ) in enumerate(SESSIONS[did], 1):
                quotes = []
                for a, b in ranges:
                    for e in evidence:
                        lo, hi = max(a, e["line_start"]), min(b, e["line_end"])
                        if lo <= hi:
                            quote = "".join(lines[lo - 1 : hi]).rstrip("\n")
                            if quote.strip():
                                quotes.append(
                                    {
                                        "evidence_id": e["evidence_id"],
                                        "quote": quote,
                                        "line_start": lo,
                                        "line_end": hi,
                                        "locator": f"{src['repository_source_url']}#L{lo}-L{hi}",
                                    }
                                )
                if not quotes:
                    raise ValueError("REFERENCE_WITHOUT_AUDITABLE_SCOPE_ANCHOR")
                text = (
                    question
                    if n > 1
                    else (
                        f'For this conversation use only the supplied unit "{course["unit"]}". '
                        "Cite evidence for factual claims and say when this unit cannot answer. "
                        + question
                    )
                )
                turns.append(
                    {
                        "text": text,
                        "category": kind,
                        "task_type": kind,
                        "answerability": "INSUFFICIENT_IN_SUPPLIED_UNIT"
                        if gap
                        else "ANSWERABLE_IN_SUPPLIED_UNIT",
                        "context_followup": bool(depends),
                        "depends_on_turns": depends,
                        "expected_topic": question
                        if not depends
                        else SESSIONS[did][depends[0] - 1][0],
                        "expected_insufficient": bool(gap),
                        "socratic": False,
                        "reference": {
                            "evidence_ids": list(
                                dict.fromkeys(q["evidence_id"] for q in quotes)
                            )
                            if not gap
                            else [],
                            "evidence_role": "scope_anchor_not_proof_of_global_absence"
                            if gap
                            else "refutes_premise"
                            if kind == "false_premise"
                            else "supports_answer_or_derivation",
                            "source_ranges": [list(r) for r in ranges],
                            "quotes": quotes,
                            "reference_points": points,
                            "allowed_answer_boundary": boundary,
                            "insufficiency_reason": gap,
                            "expected_behavior": "clean_course_bounded_abstention"
                            if gap
                            else "correct_false_premise_with_evidence"
                            if kind == "false_premise"
                            else "grounded_answer",
                            "rubric": "; ".join(points)
                            + " Boundary: "
                            + boundary
                            + " Assess all material assertions and citations; preserve referents, assumptions and dimensions. "
                            "Context consistency requires semantic review of prior turns, never string equality.",
                        },
                    }
                )
            groups[course["split"]].append(
                {
                    "dialogue_id": did,
                    "course_id": course["course_id"],
                    "lecture_id": course["course_id"],
                    "turns": turns,
                }
            )
    return snapshot, groups


def build():
    snapshot, groups = project()
    write(HERE / "snapshot.json", snapshot)
    for split, dialogues in groups.items():
        write(
            HERE / f"{split}.json",
            {"version": VERSION, "split": split, "dialogues": dialogues},
        )
    write(
        HERE / "holdout-manifest.json",
        {
            "version": VERSION,
            "policy": "COURSE_DISJOINT_EVALUATION_ONLY_NO_TUNING",
            "split_sha256": SPLIT_SHA,
            "course_ids": [
                c for c, v in snapshot["lectures"].items() if v["split"] == "holdout"
            ],
            "dialogue_ids": [d["dialogue_id"] for d in groups["holdout"]],
            "holdout_sha256": digest(HERE / "holdout.json"),
            "snapshot_sha256": digest(HERE / "snapshot.json"),
            "disclosure": "Codex authored/reviewed evaluation questions after split freeze. No product or prompt tuning. "
            "Base-model exposure unknown. No independent human expert labels or real trial outcomes.",
        },
    )
    files = [
        "course-split.json",
        "course-split.sha256",
        "sources.json",
        "author_public.py",
        "snapshot.json",
        "development.json",
        "holdout.json",
        "holdout-manifest.json",
    ]
    files += [str(p.relative_to(HERE)) for p in sorted((HERE / "materials").glob("*"))]
    write(
        HERE / "dataset-lock.json",
        {"version": VERSION, "files": {p: digest(HERE / p) for p in files}},
    )


def load():
    lock = read(HERE / "dataset-lock.json")
    if lock["version"] != VERSION or any(
        digest(HERE / p) != h for p, h in lock["files"].items()
    ):
        raise ValueError("PUBLIC_DATASET_FROZEN_INPUT_CHANGED")
    snapshot, groups = project()
    if read(HERE / "snapshot.json") != snapshot or any(
        read(HERE / f"{s}.json") != {"version": VERSION, "split": s, "dialogues": ds}
        for s, ds in groups.items()
    ):
        raise ValueError("PUBLIC_DATASET_PROJECTION_CHANGED")
    manifest = read(HERE / "holdout-manifest.json")
    if (
        manifest["holdout_sha256"] != digest(HERE / "holdout.json")
        or manifest["snapshot_sha256"] != digest(HERE / "snapshot.json")
        or manifest["dialogue_ids"] != [d["dialogue_id"] for d in groups["holdout"]]
        or manifest["course_ids"] != ["carpentries-sql"]
    ):
        raise ValueError("HOLDOUT_MANIFEST_CHANGED")
    ids, questions, evidence_ids = set(), set(), set()
    for lecture in snapshot["lectures"].values():
        for e in lecture["evidence"]:
            if e["evidence_id"] in evidence_ids:
                raise ValueError("DUPLICATE_EVIDENCE_ID")
            evidence_ids.add(e["evidence_id"])
    for split, dialogues in groups.items():
        for d in dialogues:
            if (
                d["dialogue_id"] in ids
                or snapshot["lectures"][d["lecture_id"]]["split"] != split
            ):
                raise ValueError("DUPLICATE_SESSION_OR_SPLIT_LEAK")
            ids.add(d["dialogue_id"])
            rows = {
                e["evidence_id"]: e
                for e in snapshot["lectures"][d["lecture_id"]]["evidence"]
            }
            for n, t in enumerate(d["turns"], 1):
                if t["text"] in questions or any(
                    k < 1 or k >= n for k in t["depends_on_turns"]
                ):
                    raise ValueError("DUPLICATE_QUESTION_OR_INVALID_CONTEXT")
                questions.add(t["text"])
                for q in t["reference"]["quotes"]:
                    if (
                        q["evidence_id"] not in rows
                        or q["quote"] not in rows[q["evidence_id"]]["text"]
                    ):
                        raise ValueError("REFERENCE_NOT_IN_COURSE_SOURCE")
    dev = {d["course_id"] for d in groups["development"]}
    held = {d["course_id"] for d in groups["holdout"]}
    if (
        dev & held
        or len(dev) != 2
        or len(held) != 1
        or len(ids) != 12
        or len(questions) != 60
    ):
        raise ValueError("PUBLIC_DATASET_COUNTS_OR_COURSE_ISOLATION_INVALID")
    return snapshot, groups


def select(split, courses=None, sessions=None, allow_holdout=False):
    snapshot, groups = load()
    if split not in ("development", "holdout", "all"):
        raise ValueError("EXPLICIT_SPLIT_REQUIRED")
    if split != "development" and not allow_holdout:
        raise ValueError("HOLDOUT_REQUIRES_EVALUATION_ONLY_OPT_IN")
    chosen = [d for s, ds in groups.items() if split == "all" or s == split for d in ds]
    for field, values in (("course_id", courses), ("dialogue_id", sessions)):
        if values is not None:
            if len(set(values)) != len(values) or not set(values) <= {
                d[field] for d in chosen
            }:
                raise ValueError("UNKNOWN_DUPLICATE_OR_OUT_OF_SCOPE_SELECTION")
            chosen = [d for d in chosen if d[field] in values]
    if not chosen:
        raise ValueError("EMPTY_SELECTION_NO_FULL_SCOPE_FALLBACK")
    keys = {d["lecture_id"] for d in chosen}
    return {
        **snapshot,
        "lectures": {k: v for k, v in snapshot["lectures"].items() if k in keys},
    }, chosen


def expected_rows(snapshot, scripts):
    return [
        {
            "turn_key": f"{d['dialogue_id']}:{n}",
            "dialogue_id": d["dialogue_id"],
            "ordinal": n,
            "course_id": d["course_id"],
            "split": snapshot["lectures"][d["lecture_id"]]["split"],
            "script": t,
        }
        for d in scripts
        for n, t in enumerate(d["turns"], 1)
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build",
        action="store_true",
        help="Exclusive creation; empty scratch directory only",
    )
    args = parser.parse_args()
    if args.build:
        build()
    snap, groups = load()
    print(
        json.dumps(
            {
                s: {
                    "courses": len({d["course_id"] for d in ds}),
                    "sessions": len(ds),
                    "turns": sum(len(d["turns"]) for d in ds),
                    "task_types": dict(
                        Counter(t["category"] for d in ds for t in d["turns"])
                    ),
                }
                for s, ds in groups.items()
            }
        )
    )
