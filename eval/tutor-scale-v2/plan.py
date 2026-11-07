"""A complete development-only queue; no dynamic filter or budget-derived scope."""

from pathlib import Path

from shared import BASE, HERE, digest, load, object_hash, read, verify_tooling


def validate_queue(queue, snapshot, groups, lock_sha):
    if (
        queue["dataset_version"] != read(BASE / "dataset-lock.json")["version"]
        or queue["dataset_lock_sha256"] != lock_sha
    ):
        raise ValueError("QUEUE_DATASET_VERSION_MISMATCH")
    development = {d["dialogue_id"]: d for d in groups["development"]}
    selected, seen = [], set()
    for entry in queue["sessions"]:
        did = entry["dialogue_id"]
        if did in seen or did not in development:
            raise ValueError("QUEUE_NOT_UNIQUE_DEVELOPMENT_SESSIONS")
        seen.add(did)
        d = development[did]
        if (
            entry["course_id"] != d["course_id"]
            or entry["split"] != "development"
            or snapshot["lectures"][d["lecture_id"]]["split"] != "development"
            or entry["turns"] != len(d["turns"])
            or entry["turns_sha256"] != object_hash(d["turns"])
        ):
            raise ValueError("QUEUE_SESSION_CHANGED_OR_INCOMPLETE")
        selected.append(d)
    courses = {d["course_id"] for d in selected}
    if (
        len(courses) != 2
        or len(selected) != 4
        or sum(len(d["turns"]) for d in selected) != 20
        or any(sum(d["course_id"] == c for d in selected) != 2 for c in courses)
        or queue["counts"] != {"courses": 2, "sessions": 4, "turns": 20}
    ):
        raise ValueError("QUEUE_SCOPE_INVALID")
    return selected


def load_queue(path):
    identity = verify_tooling()
    path = Path(path)
    if digest(path) != read(HERE / "queue-lock.json")["queue_sha256"]:
        raise ValueError("QUEUE_HASH_MISMATCH")
    snapshot, groups, _ = load()
    queue = read(path)
    scripts = validate_queue(queue, snapshot, groups, digest(BASE / "dataset-lock.json"))
    # Holdout evidence cannot be searched by this queue's authority.
    courses = {d["course_id"] for d in scripts}
    snapshot = {**snapshot, "lectures": {k: v for k, v in snapshot["lectures"].items() if k in courses}}
    return queue, scripts, snapshot, identity


def expected_rows(scripts):
    return [
        dict(
            turn_key=f"{d['dialogue_id']}:{n}",
            dialogue_id=d["dialogue_id"],
            ordinal=n,
            course_id=d["course_id"],
            split="development",
            script=t,
        )
        for d in scripts
        for n, t in enumerate(d["turns"], 1)
    ]
