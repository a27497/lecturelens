"""Development-only projection using the existing public dataset's block/turn contract."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VERSION = "tutor-fresh-dev-v1"
COURSES = {"carpentries-python", "carpentries-spreadsheets"}
CANDIDATE_SHA = "b7fe50df1854703cc05d4ad039dad3245cc62adc5d68c3af7b394f2407f0ec58"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def object_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def projection():
    sources = read(HERE / "sources.json")["sources"]
    if {s["course_id"] for s in sources} != COURSES or len(sources) != 2:
        raise ValueError("DEVELOPMENT_SOURCES_ONLY")
    snapshot = {
        "version": VERSION,
        "material_kind": "PUBLIC_COURSE_TEXT",
        "lectures": {},
    }
    raw = read(HERE / "questions.json")
    result = []
    for source in sources:
        if source["split"] != "development":
            raise ValueError("NO_HOLDOUT")
        for key, sha in [
            ("local_path", "sha256"),
            ("license_local_path", "license_sha256"),
        ]:
            if digest(ROOT / "eval/tutor-public-v1" / source[key]) != source[sha]:
                raise ValueError("ORIGINAL_MATERIAL_CHANGED")
        text = (ROOT / "eval/tutor-public-v1" / source["local_path"]).read_text()
        lines, evidence = text.splitlines(keepends=True), []
        # Same blank-block IDs as public v1; v11 alone groups adjacent passages.
        for match in re.finditer(r"\S[^\n]*(?:\n(?!\s*\n)[^\n]*)*", text):
            block = match.group().rstrip("\n")
            lo = text[: match.start()].count("\n") + 1
            hi = lo + block.count("\n")
            if lo <= 5 or not block.strip(": \n") or block.lstrip().startswith("![]("):
                continue
            evidence.append(
                {
                    "evidence_id": object_hash([source["sha256"], lo, hi, block]),
                    "text": block,
                    "start_ms": 0,
                    "end_ms": 0,
                    "source_type": "DOCUMENT_PAGE",
                    "course": source["course_id"],
                    "line_start": lo,
                    "line_end": hi,
                    "source_path": source["local_path"],
                    "source_url": f"{source['repository_source_url']}#L{lo}-L{hi}",
                    "content_hash": hashlib.sha256(block.encode()).hexdigest(),
                    "locator_note": "Original Markdown lines; 0/0 are NOT video timestamps or page numbers.",
                }
            )
        snapshot["lectures"][source["course_id"]] = {
            "course": source["course_id"],
            "title": source["title"],
            "split": "development",
            "attribution": source["attribution"],
            "evidence": evidence,
        }
        for session in [
            d for d in raw["dialogues"] if d["course_id"] == source["course_id"]
        ]:
            turns = []
            for ordinal, task in enumerate(session["turns"], 1):
                quotes = []
                for a, b in task["source_ranges"]:
                    if not 1 <= a <= b <= len(lines):
                        raise ValueError("BAD_REFERENCE_RANGE")
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
                                        "locator": f"{source['repository_source_url']}#L{lo}-L{hi}",
                                    }
                                )
                if not quotes:
                    raise ValueError("NO_AUDITABLE_REFERENCE")
                gap = task["insufficiency_reason"]
                deps = task["depends_on_turns"]
                if any(not 1 <= n < ordinal for n in deps):
                    raise ValueError("INVALID_DEPENDENCY")
                question = task["text"]
                if ordinal == 1:
                    question = (
                        f'Use only the supplied unit "{source["unit"]}" for this conversation. Cite course evidence for factual claims and say when it is insufficient. '
                        + question
                    )
                turns.append(
                    {
                        "text": question,
                        "category": task["task_type"],
                        "task_type": task["task_type"],
                        "tags": task["tags"],
                        "answerability": "INSUFFICIENT_IN_SUPPLIED_UNIT"
                        if gap
                        else "ANSWERABLE_IN_SUPPLIED_UNIT",
                        "context_followup": bool(deps),
                        "depends_on_turns": deps,
                        "expected_topic": task["text"],
                        "expected_insufficient": bool(gap),
                        "socratic": False,
                        "reference": {
                            "evidence_ids": []
                            if gap
                            else list(dict.fromkeys(q["evidence_id"] for q in quotes)),
                            "evidence_role": "scope_anchor_not_proof_of_global_absence"
                            if gap
                            else "supports_answer_or_correction",
                            "source_ranges": task["source_ranges"],
                            "quotes": quotes,
                            "reference_points": task["reference_points"],
                            "allowed_answer_boundary": task["allowed_answer_boundary"],
                            "insufficiency_reason": gap,
                            "expected_behavior": "clean_course_bounded_abstention"
                            if gap
                            else "grounded_answer",
                            "rubric": "; ".join(task["reference_points"])
                            + " Boundary: "
                            + task["allowed_answer_boundary"]
                            + " Assess every requested part and material added claim; require locally attached supporting citations. Judge context semantically, not by string matching.",
                        },
                    }
                )
            result.append(
                {
                    "dialogue_id": session["dialogue_id"],
                    "course_id": source["course_id"],
                    "lecture_id": source["course_id"],
                    "turns": turns,
                }
            )
    if len(result) != 4 or Counter(d["course_id"] for d in result) != {
        c: 2 for c in COURSES
    }:
        raise ValueError("FOUR_COMPLETE_DEVELOPMENT_SESSIONS_REQUIRED")
    if (
        sum(len(d["turns"]) for d in result) != 16
        or len({d["dialogue_id"] for d in result}) != 4
    ):
        raise ValueError("BATCH_SCOPE_CHANGED")
    if len({t["text"] for d in result for t in d["turns"]}) != 16:
        raise ValueError("DUPLICATE_PROMPT")
    return snapshot, {"version": VERSION, "split": "development", "dialogues": result}


def build():
    snapshot, dev = projection()
    write(HERE / "snapshot.json", snapshot)
    write(HERE / "development.json", dev)
    core = [
        "candidate-freeze.json",
        "sources.json",
        "questions.json",
        "snapshot.json",
        "development.json",
        "grading-rules.json",
    ]
    write(
        HERE / "dataset-lock.json",
        {"version": VERSION, "files": {n: digest(HERE / n) for n in core}},
    )
    freeze = read(HERE / "candidate-freeze.json")
    parts = []
    for spec in freeze["parts"]:
        scripts = [
            next(d for d in dev["dialogues"] if d["dialogue_id"] == sid)
            for sid in spec["sessions"]
        ]
        plan = {
            "dataset_version": VERSION,
            "dataset_lock_sha256": digest(HERE / "dataset-lock.json"),
            "candidate_manifest_sha256": CANDIDATE_SHA,
            "execution_authorized": False,
            "part": spec["part"],
            "counts": {"courses": 2, "sessions": 2, "turns": 8},
            "sessions": [
                {
                    "course_id": d["course_id"],
                    "dialogue_id": d["dialogue_id"],
                    "split": "development",
                    "turns": len(d["turns"]),
                    "turns_sha256": object_hash(d["turns"]),
                }
                for d in scripts
            ],
            "turn_keys": [
                f"{d['dialogue_id']}:{n}"
                for d in scripts
                for n in range(1, len(d["turns"]) + 1)
            ],
        }
        if len(plan["turn_keys"]) != 8:
            raise ValueError("PART_MUST_BE_EIGHT_COMPLETE_TURNS")
        name = f"part-{spec['part']}.json"
        write(HERE / name, plan)
        parts.append({"path": name, "sha256": digest(HERE / name)})
    write(
        HERE / "batch-plan.json",
        {
            "version": VERSION,
            "execution_authorized": False,
            "candidate_manifest_sha256": CANDIDATE_SHA,
            "dataset_lock_sha256": digest(HERE / "dataset-lock.json"),
            "counts": {"courses": 2, "sessions": 4, "turns": 16},
            "parts": parts,
            "turn_keys": [
                key for part in parts for key in read(HERE / part["path"])["turn_keys"]
            ],
        },
    )
    files = core + [
        "dataset-lock.json",
        "part-A.json",
        "part-B.json",
        "batch-plan.json",
        "data.py",
        "bridge.py",
        "batch_run.py",
        "test_batch.py",
        "CONTENT_REVIEW.json",
    ]
    write(
        HERE / "freeze-lock.json",
        {"version": VERSION, "files": {n: digest(HERE / n) for n in files}},
    )


def load():
    lock = read(HERE / "freeze-lock.json")
    if any(digest(HERE / n) != sha for n, sha in lock["files"].items()):
        raise ValueError("FROZEN_BATCH_INPUT_CHANGED")
    snapshot, dev = projection()
    if (
        read(HERE / "snapshot.json") != snapshot
        or read(HERE / "development.json") != dev
    ):
        raise ValueError("PROJECTION_CHANGED")
    if digest(ROOT / "eval/tutor-repair-v1/candidate.json") != CANDIDATE_SHA:
        raise ValueError("CANDIDATE_CHANGED")
    batch = read(HERE / "batch-plan.json")
    plans = [read(HERE / p["path"]) for p in batch["parts"]]
    for ref, plan in zip(batch["parts"], plans, strict=True):
        if digest(HERE / ref["path"]) != ref["sha256"]:
            raise ValueError("PART_HASH_CHANGED")
        selected = [
            next(d for d in dev["dialogues"] if d["dialogue_id"] == s["dialogue_id"])
            for s in plan["sessions"]
        ]
        if any(
            s["course_id"] != d["course_id"]
            or s["split"] != "development"
            or s["turns"] != len(d["turns"])
            or s["turns_sha256"] != object_hash(d["turns"])
            for s, d in zip(plan["sessions"], selected, strict=True)
        ):
            raise ValueError("PART_SESSION_CHANGED")
        if plan["turn_keys"] != [
            f"{d['dialogue_id']}:{n}"
            for d in selected
            for n in range(1, len(d["turns"]) + 1)
        ]:
            raise ValueError("PART_INCOMPLETE")
    if len(set(batch["turn_keys"])) != 16 or any(
        p["execution_authorized"] is not False for p in [batch, *plans]
    ):
        raise ValueError("SCOPE_OR_AUTHORIZATION_INVALID")
    return batch, dev["dialogues"], snapshot


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--build", action="store_true")
    a = p.parse_args()
    if a.build:
        build()
    batch, scripts, snapshot = load()
    print(
        json.dumps(
            {
                "counts": batch["counts"],
                "course_ids": list(snapshot["lectures"]),
                "answerable": sum(
                    not t["expected_insufficient"] for d in scripts for t in d["turns"]
                ),
                "task_types": dict(
                    Counter(t["task_type"] for d in scripts for t in d["turns"])
                ),
                "plan_sha256": digest(HERE / "batch-plan.json"),
            }
        )
    )
