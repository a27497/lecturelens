"""Create this new queue/candidate once; never overwrite any existing manifest."""

from shared import BASE, HERE, ROOT, digest, load, object_hash, write

if __name__ == "__main__":
    _, groups, _ = load()
    chosen = ["queue-03", "queue-09", "ecology-02", "ecology-08"]
    by_id = {d["dialogue_id"]: d for d in groups["development"]}
    write(
        HERE / "development-queue-v1.json",
        dict(
            queue_version="tutor-development-pilot-v1",
            dataset_version="tutor-scale-synthetic-v2",
            dataset_lock_sha256=digest(BASE / "dataset-lock.json"),
            counts=dict(courses=2, sessions=4, turns=20),
            sessions=[
                dict(
                    dialogue_id=did,
                    course_id=by_id[did]["course_id"],
                    split="development",
                    turns=len(by_id[did]["turns"]),
                    turns_sha256=object_hash(by_id[did]["turns"]),
                )
                for did in chosen
            ],
            review_overlap_turns=["queue-03:1", "queue-03:2", "queue-09:3", "ecology-02:4", "ecology-08:5"],
            scope_policy="COMPLETE_DEVELOPMENT_SESSIONS_ONLY_NO_FALLBACK_NO_HOLDOUT",
        ),
    )
    write(HERE / "queue-lock.json", dict(queue_sha256=digest(HERE / "development-queue-v1.json")))
    paths = [p for p in HERE.glob("*.py")] + [
        HERE / "README.md",
        HERE / "development-queue-v1.json",
        HERE / "queue-lock.json",
    ]
    write(
        HERE / "candidate.json",
        dict(
            candidate="tutor-scale-preparation-v2",
            base_commit="74208e10b37583b951cf2a45a0b644bfed11b902",
            previous_candidate_sha256=digest(BASE / "candidate.json"),
            files={str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)},
            status="MOCK_PREPARATION_ONLY_REAL_QUALITY_NOT_RUN",
        ),
    )
