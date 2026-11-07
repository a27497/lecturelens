"""Build and verify the additive, synthetic Tutor scale dataset."""

import hashlib
import json
from pathlib import Path

from author import COURSES

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VERSION = "tutor-scale-synthetic-v2"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    with Path(path).open("x") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build():
    groups = {"development": [], "holdout": []}
    snapshot = {
        "license": "CC0-1.0",
        "material_kind": "ORIGINAL_SYNTHETIC",
        "lectures": {},
    }
    for key, (title, split, lessons) in COURSES.items():
        evidence = []
        for i, row in enumerate(lessons, 1):
            fact, *questions = row
            eid = hashlib.sha256(f"{key}:{i}:{fact}".encode()).hexdigest()
            source = f"eval/tutor-scale/snapshot.json#/lectures/{key}/evidence/{i - 1}"
            evidence.append(
                dict(
                    evidence_id=eid,
                    text=fact,
                    start_ms=i * 1000,
                    end_ms=(i + 1) * 1000,
                    source_type="DOCUMENT_PAGE",
                    section=i,
                    course=key,
                    source_url=source,
                    content_hash=hashlib.sha256(fact.encode()).hexdigest(),
                    locator_note="Synthetic section slots, not timestamps",
                )
            )
            turns = []
            for n, (question, category) in enumerate(
                zip(
                    questions,
                    [
                        "fact",
                        "followup",
                        "false_premise",
                        "insufficient",
                        "out_of_scope",
                    ],
                    strict=True,
                ),
                1,
            ):
                negative = n >= 4
                turns.append(
                    dict(
                        text=question,
                        category=category,
                        context_followup=n in (2, 3),
                        expected_topic=questions[0],
                        expected_insufficient=negative,
                        socratic=False,
                        reference=dict(
                            evidence_ids=[] if negative else [eid],
                            locator=source,
                            quote=fact,
                            expected_behavior="clean_abstention"
                            if negative
                            else ("correct_false_premise" if n == 3 else "grounded_answer"),
                            rubric=(
                                "Do not invent the requested parameter or give an outside-course answer; "
                                "an exact clean abstention is acceptable."
                                if negative
                                else "Answer the specific question using the section facts; preserve conditions, "
                                "units and prior referents; cite supporting assertions. "
                                "For false premises explicitly correct the mistaken assertion."
                            ),
                        ),
                    )
                )
            groups[split].append(
                dict(
                    dialogue_id=f"{key}-{i:02d}",
                    course_id=key,
                    lecture_id=key,
                    turns=turns,
                )
            )
        snapshot["lectures"][key] = dict(
            course=key,
            title=title,
            split=split,
            attribution="Original fictional teaching fixtures authored for LectureLens evaluation; "
            "CC0-1.0; no external content, model generation or student records.",
            evidence=evidence,
        )
    write(HERE / "snapshot.json", snapshot)
    for split, dialogues in groups.items():
        write(
            HERE / f"{split}.json",
            dict(version=VERSION, split=split, dialogues=dialogues),
        )
    write(
        HERE / "holdout-manifest.json",
        dict(
            version=VERSION,
            policy="COURSE_DISJOINT_FROZEN_NO_TUNING",
            course_ids=["energy"],
            dialogue_ids=[d["dialogue_id"] for d in groups["holdout"]],
            dataset_sha256=digest(HERE / "holdout.json"),
            snapshot_sha256=digest(HERE / "snapshot.json"),
            note="Withheld from product/prompt development. Public synthetic content; base-model exposure is unknown. "
            "Mock execution is mechanics only and does not consume semantic quality trials. "
            "After first real trial retain failures and never tune on these outcomes; use a fresh future holdout.",
        ),
    )
    write(
        HERE / "dataset-lock.json",
        dict(
            version=VERSION,
            files={
                p: digest(HERE / p)
                for p in (
                    "author.py",
                    "development.json",
                    "holdout.json",
                    "snapshot.json",
                    "holdout-manifest.json",
                )
            },
        ),
    )


def load():
    lock = json.loads((HERE / "dataset-lock.json").read_text())
    for path, expected in lock["files"].items():
        if digest(HERE / path) != expected:
            raise ValueError("DATASET_CHANGED")
    snapshot = json.loads((HERE / "snapshot.json").read_text())
    groups = {
        s: json.loads((HERE / f"{s}.json").read_text())["dialogues"] for s in ("development", "holdout")
    }
    seen, questions = set(), set()
    for split, dialogues in groups.items():
        for d in dialogues:
            assert d["dialogue_id"] not in seen
            seen.add(d["dialogue_id"])
            lecture = snapshot["lectures"][d["lecture_id"]]
            assert lecture["split"] == split and len(d["turns"]) == 5
            rows = {r["evidence_id"]: r for r in lecture["evidence"]}
            for t in d["turns"]:
                assert t["text"] not in questions
                questions.add(t["text"])
                for eid in t["reference"]["evidence_ids"]:
                    assert t["reference"]["quote"] in rows[eid]["text"]
    manifest = json.loads((HERE / "holdout-manifest.json").read_text())
    assert manifest["dialogue_ids"] == [d["dialogue_id"] for d in groups["holdout"]]
    assert manifest["dataset_sha256"] == digest(HERE / "holdout.json")
    assert manifest["snapshot_sha256"] == digest(HERE / "snapshot.json")
    assert not {d["course_id"] for d in groups["development"]} & {d["course_id"] for d in groups["holdout"]}
    counts = {
        s: dict(
            courses=len({d["course_id"] for d in ds}),
            sessions=len(ds),
            turns=sum(len(d["turns"]) for d in ds),
        )
        for s, ds in groups.items()
    }
    assert sum(v["turns"] for v in counts.values()) >= 300 and len(snapshot["lectures"]) in range(3, 6)
    return snapshot, groups, counts


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["build"]:
        build()
    print(json.dumps(load()[2]))
