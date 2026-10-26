"""Offline measurement: scoped, read-only lab export; arithmetic over independent ratings.

No model client is constructed. Student statements and source checks live in a sidecar;
these are observations, never inferred from 'acknowledged' or a changed answer.
"""

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LABELS = {"correct", "incorrect", "missing", "unsupported"}
SETS = ("detected", "supported", "feedback_flagged")
FLAGS = (
    "feedback_wrong",
    "accepted_wrong_feedback",
    "false_refusal",
    "honest_insufficiency",
)


def load(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    # Exclusive creation preserves failed trials and prevents silently replacing evidence.
    with Path(path).open("x") as out:
        out.write(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()


def verify_freeze(root=ROOT):
    frozen = load(root / "FREEZE.json")
    for relative, expected in frozen["files"].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen input changed: {relative}")
    return hashlib.sha256((root / "FREEZE.json").read_bytes()).hexdigest()


def safe_lab_dsn(dsn):
    from psycopg.conninfo import conninfo_to_dict

    config = conninfo_to_dict(dsn)
    if (
        config.get("host") not in {"127.0.0.1", "localhost", "::1"}
        or config.get("hostaddr") not in {None, "127.0.0.1", "::1"}
        or config.get("service")
        or not config.get("dbname", "").startswith("lecturelens_p6_")
        or not config["dbname"].endswith("_test")
    ):
        raise ValueError(
            "Only an explicit loopback lecturelens_p6_*_test database is allowed"
        )
    return dsn


def timestamp(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("UTC offset required")
    return result


def bound_sources(spec, course):
    canonical = {e["evidence_id"]: e for e in course["evidence"]}
    scope = spec["scope"]
    if spec["data_kind"] == "MOCK":
        if scope["revision"] != course["revision"]:
            raise ValueError("Course snapshot revision mismatch")
        if not scope["course_id"].startswith(course["course_key"]):
            raise ValueError("Mock course scope mismatch")
        return canonical, {key: key for key in canonical}
    if spec["data_kind"] != "PILOT":
        raise ValueError("Unknown data provenance")
    binding = spec["source_binding"]
    if (
        binding["course_id"] != scope["course_id"]
        or binding["revision"] != scope["revision"]
        or binding["material_hash"] != digest(course)
        or binding["acquired_via"] != "authenticated_java_evidence"
    ):
        raise ValueError("Pilot source binding scope mismatch")
    sources, mapping = {}, {}
    seen = set()
    for row in binding["sources"]:
        key, actual = row["canonical_id"], row["authority_evidence"]
        if key not in canonical or key in seen or actual["evidence_id"] in sources:
            raise ValueError("Ambiguous source identity")
        if actual["text"] != canonical[key]["text"]:
            raise ValueError(
                "Pilot source text differs from frozen material; quarantine trial"
            )
        sources[actual["evidence_id"]] = actual
        mapping[actual["evidence_id"]] = key
        seen.add(key)
    if seen != canonical.keys():
        raise ValueError("Pilot material coverage incomplete")
    return sources, mapping


def export_trial(store, spec, course):
    from lecturelens_agent.study.contracts import StudyCommand

    scope = spec["scope"]
    evidence, source_map = bound_sources(spec, course)

    def command(operation, **kwargs):
        return store.command(
            StudyCommand(**(scope | kwargs | {"operation": operation})), "mock"
        )

    parent = command("READ")
    if parent["run"]["model_mode"] != "mock" and spec["data_kind"] == "MOCK":
        raise ValueError("Mock label cannot hide real run")
    questions = parent["artifact"]["questions"]
    if questions[scope["question_index"]]["question"] != spec["question"]:
        raise ValueError("Frozen question does not match persisted artifact")
    history, cursor = [], None
    while True:
        page = command(
            "ATTEMPT_HISTORY", **({"before_version": cursor} if cursor else {})
        )
        history.extend(page["attempts"])
        cursor = page["next_before_version"]
        if cursor is None:
            break
    by_id = {a["attempt_id"]: a for a in history}
    first, final = [by_id[spec[k]] for k in ("initial_attempt_id", "final_attempt_id")]
    if final["version"] <= first["version"]:
        raise ValueError("Final answer must be a later immutable version")
    if timestamp(spec["discovery"]["at"]) < timestamp(first["created_at"]) or timestamp(
        spec["discovery"]["at"]
    ) > timestamp(final["created_at"]):
        raise ValueError("Discovery must be recorded between initial and final answers")
    for check in spec["source_checks"]:
        if check["evidence_id"] not in evidence:
            raise ValueError("Unknown source check")
        if (
            not timestamp(first["created_at"])
            <= timestamp(check["at"])
            <= timestamp(final["created_at"])
        ):
            raise ValueError("Source check outside intervention")
    final_evidence = spec["final_evidence"]
    if final_evidence["attempt_id"] != final["attempt_id"]:
        raise ValueError("Evidence rationale belongs to a different final answer")
    for claim in final_evidence["claims"]:
        if (
            not claim["reason"].strip()
            or not set(claim["evidence_ids"]) <= evidence.keys()
        ):
            raise ValueError("Invalid student evidence rationale")
    feedback = []
    for exposure in spec["feedback_exposures"]:
        response = command("READ", run_id=exposure["run_id"])
        f = response["feedback"]
        if (
            f is None
            or f["feedback_id"] != exposure["feedback_id"]
            or f["attempt_id"] != first["attempt_id"]
            or f["answer_version"] != first["version"]
        ):
            raise ValueError("Feedback belongs to a different initial answer")
        if exposure["answer_version_at_exposure"] != f["answer_version"]:
            raise ValueError(
                "Stale feedback exposure cannot be treated as current feedback"
            )
        if (
            not timestamp(first["created_at"])
            <= timestamp(exposure["at"])
            <= timestamp(final["created_at"])
        ):
            raise ValueError("Feedback exposure outside intervention")
        notes, cursor = [], None
        while True:
            page = command(
                "FEEDBACK_NOTES",
                run_id=exposure["run_id"],
                feedback_id=f["feedback_id"],
                **({"before_version": cursor} if cursor else {}),
            )
            notes.extend(page["notes"])
            cursor = page["next_before_version"]
            if cursor is None:
                break
        for citation in f["content"].get("citations", []):
            if (
                citation["evidence_id"] not in evidence
                or citation["text"] != evidence[citation["evidence_id"]]["text"]
            ):
                raise ValueError("Citation snapshot mismatch")
        feedback.append(
            {
                "run": response["run"],
                "feedback": f,
                "notes": notes,
                "exposure": exposure,
                "stale_after_revision": final["version"] != f["answer_version"],
            }
        )
    if spec["condition"] not in {"reading", "feedback"}:
        raise ValueError("Unknown condition")
    if (spec["condition"] == "reading" and feedback) or (
        spec["condition"] == "feedback" and not feedback
    ):
        raise ValueError("Condition contamination or missing feedback exposure")
    if spec["condition"] == "reading" and parent["feedback_runs"]:
        raise ValueError("Control run has feedback; quarantine this trial")
    return {
        "trial_id": spec["trial_id"],
        "item_id": spec["item_id"],
        "condition": spec["condition"],
        "data_kind": spec["data_kind"],
        "scope": scope,
        "initial": first,
        "final": final,
        "history": history,
        "parent_run": parent["run"],
        "question": spec["question"],
        "feedback": feedback,
        "sidecar": spec,
        "course_snapshot": course,
        "source_id_map": source_map,
    }


def validate_rating(row, item):
    facts = {f["id"] for f in item["facts"]}
    for stage in ("initial", "final"):
        if set(row[stage]) != facts or any(
            label not in LABELS for label in row[stage].values()
        ):
            raise ValueError("Incomplete fact labels")
    for field in SETS:
        if len(row[field]) != len(set(row[field])) or not set(row[field]) <= facts:
            raise ValueError("Unknown or duplicate fact in rating")
    if not set(row["supported"]) <= {
        k for k, v in row["final"].items() if v == "correct"
    }:
        raise ValueError("Evidence support requires a correct final fact")
    if any(
        row["initial"][f] == "correct"
        for f in row["detected"] + row["feedback_flagged"]
    ):
        raise ValueError("Correct initial fact cannot be a discovered error")
    for flag in FLAGS:
        if row[flag] is not None and type(row[flag]) is not bool:
            raise ValueError("Flags must be boolean or null")
    if not row["rationale"].strip():
        raise ValueError("Independent scoring rationale required")


def rate(numerator, denominator):
    return {
        "n": numerator,
        "d": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def score(export, ratings, standard):
    if export["freeze_hash"] != verify_freeze():
        raise ValueError("Export and frozen standard identity differ")
    if standard not in [
        load(ROOT / split / "standard.json") for split in ("development", "holdout")
    ]:
        raise ValueError("Scoring must use an unchanged frozen standard")
    items = {i["item_id"]: i for i in standard["items"]}
    rows = {r["trial_id"]: r for r in ratings}
    trials = export["trials"]
    if len({t["trial_id"] for t in trials}) != len(trials):
        raise ValueError("Duplicate exported trial")
    if any(t["data_kind"] != export["data_kind"] for t in trials):
        raise ValueError("Mixed mock and learner data")
    if any(t["condition"] not in {"reading", "feedback"} for t in trials):
        raise ValueError("Unknown experimental condition")
    incomplete = export.get("incomplete_trials", [])
    if (
        any(t["condition"] not in {"reading", "feedback"} for t in incomplete)
        or len({t["trial_id"] for t in incomplete}) != len(incomplete)
        or {t["trial_id"] for t in incomplete} & {t["trial_id"] for t in trials}
    ):
        raise ValueError("Invalid incomplete-trial accounting")
    if len(rows) != len(ratings) or set(rows) != {t["trial_id"] for t in trials}:
        raise ValueError("Ratings must cover each exported trial exactly once")
    result = {
        "warning": "Mock 数据，不代表教学效果"
        if export["data_kind"] == "MOCK"
        else "描述性统计；不代表因果或显著性",
        "data_kind": export["data_kind"],
        "export_hash": digest(export),
        "ratings_hash": digest(ratings),
        "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "freeze_hash": verify_freeze(),
        "incomplete_trials": export.get("incomplete_trials", []),
        "scoring_origin": "SCRIPTED_EXAMPLE_NOT_HUMAN"
        if export["data_kind"] == "MOCK"
        else "INDEPENDENT_RATINGS",
        "conditions": {},
    }
    for condition in ("reading", "feedback"):
        count = Counter()
        case_rows = []
        for trial in trials:
            if trial["condition"] != condition:
                continue
            row, item = rows[trial["trial_id"]], items[trial["item_id"]]
            validate_rating(row, item)
            if row["item_id"] != trial["item_id"]:
                raise ValueError("Rating task mismatch")
            claims = {
                c["fact_id"]: c for c in trial["sidecar"]["final_evidence"]["claims"]
            }
            for fact in item["facts"]:
                if fact["id"] in row["supported"] and (
                    fact["id"] not in claims
                    or not set(fact["required_evidence"])
                    <= {
                        trial.get("source_id_map", {}).get(key, key)
                        for key in claims[fact["id"]]["evidence_ids"]
                    }
                ):
                    raise ValueError(
                        "Supported rating lacks student evidence and rationale"
                    )
            if row["detected"] and not trial["sidecar"]["discovery"]["text"].strip():
                raise ValueError("Discovery rating lacks student statement")
            if condition == "reading" and (
                row["feedback_flagged"] or any(row[k] is not None for k in FLAGS[:3])
            ):
                raise ValueError("Control feedback fields must be not applicable")
            if condition == "feedback" and any(
                type(row[k]) is not bool for k in FLAGS[:3]
            ):
                raise ValueError("Feedback fields require independent judgments")
            if item["insufficient"] != (type(row["honest_insufficiency"]) is bool):
                raise ValueError(
                    "Honesty is rated only for insufficient-evidence tasks"
                )
            wrong = {k for k, v in row["initial"].items() if v != "correct"}
            corrected = {k for k in wrong if row["final"][k] == "correct"}
            initially_correct = set(row["initial"]) - wrong
            degraded = {k for k in initially_correct if row["final"][k] != "correct"}
            count.update(
                trials=1,
                facts=len(row["initial"]),
                initial_correct=len(initially_correct),
                final_correct=sum(v == "correct" for v in row["final"].values()),
                initial_errors=len(wrong),
                detected=len(set(row["detected"]) & wrong),
                corrected=len(corrected),
                supported_corrections=len(corrected & set(row["supported"])),
                degraded=len(degraded),
                fully_correct=all(v == "correct" for v in row["final"].values()),
                feedback_wrong=int(row["feedback_wrong"] is True),
                accepted_wrong=int(row["accepted_wrong_feedback"] is True),
                missed_errors=len(wrong - set(row["feedback_flagged"])),
                retained_missed=len((wrong - set(row["feedback_flagged"])) - corrected),
                sufficient=int(not item["insufficient"]),
                false_refusal=int(row["false_refusal"] is True),
                insufficient=int(item["insufficient"]),
                honest=int(row["honest_insufficiency"] is True),
            )
            case_rows.append(
                {
                    "trial_id": trial["trial_id"],
                    "initial_errors": sorted(wrong),
                    "corrected": sorted(corrected),
                    "degraded": sorted(degraded),
                    "rating": row,
                }
            )
        c = count
        assigned = c["trials"] + sum(t["condition"] == condition for t in incomplete)
        result["conditions"][condition] = {
            "completed_trials": c["trials"],
            "assigned_trials": assigned,
            "completion": rate(c["trials"], assigned),
            "conservative_fully_correct": rate(c["fully_correct"], assigned),
            "initial_factual_accuracy": rate(c["initial_correct"], c["facts"]),
            "error_discovery": rate(c["detected"], c["initial_errors"]),
            "final_factual_accuracy": rate(c["final_correct"], c["facts"]),
            "fully_correct_final_answers": rate(c["fully_correct"], c["trials"]),
            "correction_rate": rate(c["corrected"], c["initial_errors"]),
            "evidence_supported_corrections": rate(
                c["supported_corrections"], c["corrected"]
            ),
            "correct_to_wrong_transition": rate(c["degraded"], c["initial_correct"]),
            "feedback_misleading_transition": rate(c["degraded"], c["initial_correct"])
            if condition == "feedback"
            else None,
            "feedback_wrong_trials": rate(c["feedback_wrong"], c["trials"])
            if condition == "feedback"
            else None,
            "wrong_feedback_acceptance": rate(c["accepted_wrong"], c["feedback_wrong"])
            if condition == "feedback"
            else None,
            "feedback_missed_errors": rate(c["missed_errors"], c["initial_errors"])
            if condition == "feedback"
            else None,
            "retained_missed_errors": rate(c["retained_missed"], c["missed_errors"])
            if condition == "feedback"
            else None,
            "false_refusal": rate(c["false_refusal"], c["sufficient"])
            if condition == "feedback"
            else None,
            "honest_insufficiency": rate(c["honest"], c["insufficient"]),
            "cases": case_rows,
        }
    return result


def agreement(left, right, standard):
    verify_freeze()
    if standard not in [
        load(ROOT / split / "standard.json") for split in ("development", "holdout")
    ]:
        raise ValueError("Agreement must use an unchanged frozen standard")
    l, r = {x["trial_id"]: x for x in left}, {x["trial_id"]: x for x in right}
    if len(l) != len(left) or len(r) != len(right) or l.keys() != r.keys() or not l:
        raise ValueError("Two independent raters must cover the same nonempty trials")
    items = {i["item_id"]: i for i in standard["items"]}
    pairs, extras = [], []
    for key in sorted(l):
        if (
            l[key]["rater_id"] == r[key]["rater_id"]
            or l[key]["item_id"] != r[key]["item_id"]
        ):
            raise ValueError("Different raters and same task required")
        for row in (l[key], r[key]):
            validate_rating(row, items[row["item_id"]])
        for stage in ("initial", "final"):
            pairs.extend(
                (l[key][stage][f], r[key][stage][f]) for f in sorted(l[key][stage])
            )
        for field in SETS + FLAGS:
            a, b = l[key][field], r[key][field]
            extras.append((field, set(a) == set(b) if field in SETS else a == b))
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    lc, rc = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(lc[x] * rc[x] for x in LABELS) / n**2
    return {
        "fact_labels": n,
        "raw_agreement": observed,
        "cohen_kappa": (observed - expected) / (1 - expected) if expected < 1 else None,
        "other_field_agreement": {
            field: rate(sum(ok for f, ok in extras if f == field), len(l))
            for field in SETS + FLAGS
        },
        "note": "脚本示例评分不可冒充真人双评；裁决前计算一致性并保留原分。",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify", "export", "score", "agreement"])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--ratings", type=Path)
    parser.add_argument("--second-ratings", type=Path)
    parser.add_argument("--course", type=Path, default=ROOT / "development/course.json")
    parser.add_argument(
        "--standard", type=Path, default=ROOT / "development/standard.json"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    frozen = verify_freeze()
    if args.action == "verify":
        print(f"Frozen inputs verified: {frozen}")
        return
    if args.action == "export":
        from lecturelens_agent.study.store import StudyStore

        spec = load(args.input)
        store = StudyStore(safe_lab_dsn(os.environ["AGENT_TEST_DATABASE_URL"]))
        course = load(args.course)
        if course not in [
            load(ROOT / split / "course.json") for split in ("development", "holdout")
        ]:
            raise ValueError("Export requires an unchanged frozen course snapshot")
        result = {
            "data_kind": spec["data_kind"],
            "freeze_hash": frozen,
            "trials": [export_trial(store, trial, course) for trial in spec["trials"]],
            "incomplete_trials": spec.get("incomplete_trials", []),
        }
    elif args.action == "score":
        result = score(load(args.input), load(args.ratings), load(args.standard))
    else:
        result = agreement(
            load(args.ratings), load(args.second_ratings), load(args.standard)
        )
    write_new(args.output, result)


if __name__ == "__main__":
    main()
