"""Inspect frozen coverage and execution separately from independent teaching review."""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ABSTENTION = (
    "I don't know from this course. Try asking about a topic covered in this lecture."
)
PROTOCOL_ERRORS = {
    "TUTOR_FLASH_INVALID_ENVELOPE",
    "TUTOR_FLASH_INVALID_JSON",
    "TUTOR_FLASH_BLANK",
    "TUTOR_FLASH_TRUNCATED",
    "TUTOR_FLASH_INTERRUPTED",
    "TUTOR_PROTOCOL_FAILURE",
    "TUTOR_CITATION_MISMATCH",
    "TUTOR_ABSTENTION_CONTRACT",
    "TUTOR_SOURCE_ONLY",
    "TUTOR_FOCUS_REQUIRED",
}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def authority_text(text):
    # Java evidence-v1 uses ASCII regex whitespace, then String.strip and a 1200 UTF-16-unit cap.
    normalized = re.sub(r"[ \t\n\x0b\f\r]+", " ", text).strip()
    assert len(normalized.encode("utf-16-le")) <= 2400, (
        "Frozen excerpt exceeds the authority cap"
    )
    return normalized


def read_dataset():
    return json.loads((HERE / "dataset.json").read_bytes())


def read_archive(dataset, path):
    source = dataset["sources"]["loop"]
    assert sha(path.read_bytes()) == source["archive_sha256"]
    with zipfile.ZipFile(path) as archive:
        for name, expected in source["archive_members_sha256"].items():
            assert sha(archive.read(name)) == expected, name
        evidence = {
            row["evidence_id"]: row["text"]
            for row in json.loads(archive.read("course-evidence.json"))["evidence"]
        }
        outcomes = json.loads(archive.read("outcomes.json"))
    assert len(outcomes) == 3
    for turn, row in zip(dataset["dialogues"][0]["turns"], outcomes, strict=True):
        assert (turn["question"], turn["socratic"]) == (
            row["learner_text"],
            row["socratic"],
        )
        old = turn["historical"]
        assert (old["turn_key"], old["status"], old["error_code"]) == (
            row["turn_key"],
            row["status"],
            row["error_code"],
        )
    return {
        key: evidence[item["archive_evidence_id"]]
        for key, item in source["evidence"].items()
    }


def packet(dataset, source_key, historic):
    source = dataset["sources"][source_key]
    excerpts = (
        historic
        if source_key == "loop"
        else {key: item["text"] for key, item in source["evidence"].items()}
    )
    for key, text in excerpts.items():
        assert sha(text.encode()) == source["evidence"][key]["sha256"], key
        authority_text(text)
    return excerpts


def coverage(case, excerpts, observed):
    by_text = {authority_text(text): key for key, text in excerpts.items()}
    mapped, unknown_ids = {}, []
    for row in observed:
        key = by_text.get(row["text"])
        if key:
            mapped[row["evidence_id"]] = key
        else:
            unknown_ids.append(row["evidence_id"])
    delivered = set(mapped.values())
    groups = [set(group) for group in case["required_evidence"]]
    missing = [sorted(group) for group in groups if not group & delivered]
    if unknown_ids:
        label = "UNMAPPED"
    elif not groups:
        label = "EXPECTED_GAP"
    elif not missing:
        label = "FULL"
    elif len(missing) == len(groups):
        label = "MISS"
    else:
        label = "PARTIAL"
    return {
        "coverage": label,
        "missing_any_of": missing,
        "observed": mapped,
        "unmapped_ids": unknown_ids,
    }


def diagnose(case, excerpts, turn):
    state = turn["checkpoint"]
    assert (turn["learner_text"], turn["socratic"]) == (
        case["question"],
        case["socratic"],
    )
    retrieval = (
        coverage(case, excerpts, state["evidence"])
        if "evidence" in state
        else {"coverage": "UNOBSERVED"}
    )
    if turn["status"] == "completed":
        execution = "GENERATED" if turn["model_calls"] else "DETERMINISTIC"
    elif turn["error_code"] in PROTOCOL_ERRORS:
        execution = "PROTOCOL_FAILURE"
    elif turn["status"] in {"failed", "cancelled"}:
        execution = "EXECUTION_FAILURE"
    else:
        execution = "INCOMPLETE"
    review = "NOT_SCORED"
    if execution == "GENERATED" and retrieval["coverage"] in {"FULL", "EXPECTED_GAP"}:
        review = "INDEPENDENT_REVIEW_REQUIRED"
    return {
        **retrieval,
        "execution": execution,
        "error_code": turn["error_code"],
        "outcome": turn["outcome"],
        "semantic_quality": review,
    }


def verify(dataset, historic, upstream):
    cases = {}
    for dialogue in dataset["dialogues"]:
        source = dialogue["source"]
        excerpts = packet(dataset, source, historic)
        for case in dialogue["turns"]:
            assert case["id"] not in cases and case["required_checks"]
            assert case["socratic"] == (case["expected_outcome"] == "socratic_prompt")
            assert bool(case["required_evidence"]) == (
                case["expected_outcome"] != "insufficient_evidence"
            )
            assert all(
                group and set(group) <= set(excerpts)
                for group in case["required_evidence"]
            )
            cases[case["id"]] = (case, excerpts)
    for key, source in dataset["sources"].items():
        if key == "loop" or upstream is None:
            continue
        raw = (upstream / f"{key}.md").read_bytes()
        assert sha(raw) == source["upstream_sha256"]
        lines = raw.decode().splitlines()
        for item in source["evidence"].values():
            start, end = item["lines"]
            assert "\n".join(lines[start - 1 : end]) == item["text"]
    for control in dataset["review_controls"]:
        case, excerpts = cases[control["case"]]
        observed = [
            {"evidence_id": key, "text": authority_text(excerpts[key])}
            for key in control["evidence"]
        ]
        assert (
            coverage(case, excerpts, observed)["coverage"]
            == control["expected_retrieval"]
        )
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument(
        "--upstream-dir",
        type=Path,
        help="Optional exact upstream sql.md, shell.md and git.md",
    )
    parser.add_argument(
        "--journal",
        type=Path,
        help="Object mapping frozen case id to a full PG turn row",
    )
    args = parser.parse_args()
    dataset = read_dataset()
    historic = read_archive(dataset, args.archive)
    cases = verify(dataset, historic, args.upstream_dir)
    output = {
        "dataset_sha256": sha((HERE / "dataset.json").read_bytes()),
        "case_count": len(cases),
        "historical_archive_verified": True,
        "full_upstream_verified": args.upstream_dir is not None,
        "real_model_quality": "NOT_RUN",
    }
    if args.journal:
        turns = json.loads(args.journal.read_bytes())
        output["quality_review"] = "UNSCORED"
        output["coverage_by_case"] = {
            key: diagnose(*cases[key], row) for key, row in turns.items()
        }
        output["unobserved_cases"] = sorted(set(cases) - set(turns))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
