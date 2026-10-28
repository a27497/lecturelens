"""Break latest-version and scope predicates; require failing regressions and restore bytes."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
output = Path(sys.argv[1]).resolve()
output.mkdir(parents=True, exist_ok=True)
path = ROOT / "agent-service/src/lecturelens_agent/study/choice_review.py"
original = path.read_bytes()
base = "tests/test_choice_review.py::"
cases = [
    (
        "oldest-version",
        b"a.version DESC",
        b"a.version ASC",
        base + "test_latest_correct_version_removes_wrong_question_and_wrong_again_uses_latest",
    ),
    (
        "owner-fence",
        b"s.owner_id=%s",
        b"(%s::bigint IS NOT NULL)",
        base + "test_owner_course_revision_fences_prevent_record_and_count_disclosure",
    ),
    (
        "course-fence",
        b"s.course_id=%s",
        b"(%s::text IS NOT NULL)",
        base + "test_owner_course_revision_fences_prevent_record_and_count_disclosure",
    ),
    (
        "revision-fence",
        b"s.revision=%s",
        b"(%s::bigint IS NOT NULL)",
        base + "test_owner_course_revision_fences_prevent_record_and_count_disclosure",
    ),
]
records = []


def run(name, tests):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/dev/run_check.py"),
            "--name",
            name,
            "--timeout",
            "300",
            "--output",
            str(output),
            "--",
            "/home/dev/.local/bin/uv",
            "run",
            "pytest",
            "-q",
            *tests,
        ],
        cwd=ROOT / "agent-service",
        env=os.environ,
        check=False,
    ).returncode


for name, before, after, test in cases:
    assert original.count(before) == 1
    try:
        path.write_bytes(original.replace(before, after))
        code = run(name, [test])
        log = (output / (name + ".log")).read_text()
        assert code == 1 and "AssertionError" in log and "failed" in log, (name, code)
    finally:
        path.write_bytes(original)
        for cached in (path.parent / "__pycache__").glob(path.stem + ".*.pyc"):
            cached.unlink()
    assert path.read_bytes() == original
    records.append(dict(name=name, expected_exit=1, actual_exit=code, test=test))
code = run("restored", ["tests/test_choice_review.py"])
assert code == 0
(output / "results.json").write_text(
    json.dumps(
        dict(
            sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            mutations=records,
            restored_exit=code,
            restored_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        ),
        indent=2,
    )
    + "\n"
)
print("All four predicate mutations caught; original restored and review tests pass.")
