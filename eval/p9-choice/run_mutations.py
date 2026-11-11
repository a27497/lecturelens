"""Negative controls run against an explicit disposable PG; always restore source bytes."""

import difflib
import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT / "agent-service/src/lecturelens_agent/study/choice.py"
original = SOURCE.read_bytes()
results = []
if not os.environ.get("AGENT_TEST_DATABASE_URL"):
    raise RuntimeError("Independent test PG required")


def invalidate_bytecode():
    for path in (SOURCE.parent / "__pycache__").glob("choice.*.pyc"):
        path.unlink()


def run(name, expression):
    command = [
        str(ROOT / "agent-service/.venv/bin/python"),
        "-m",
        "pytest",
        "-q",
        "agent-service/tests/test_study_choices.py",
    ]
    if expression:
        command += ["-k", expression]
    wrapped = [
        sys.executable,
        "scripts/dev/run_check.py",
        "--name",
        name,
        "--timeout",
        "180",
        "--output",
        str(OUT),
        "--",
        *command,
    ]
    return subprocess.run(wrapped, cwd=ROOT, check=False).returncode, command


try:
    # Break the READ/ANSWERS positive allowlist, without changing the frozen manifest.
    text = original.decode()
    bad = text.replace(
        '"kind", "options")', '"kind", "options", "correct_option_id")', 1
    )
    assert bad != text
    SOURCE.write_text(bad)
    invalidate_bytecode()
    (OUT / "privacy.diff").write_text(
        "".join(
            difflib.unified_diff(
                text.splitlines(keepends=True),
                bad.splitlines(keepends=True),
                fromfile="choice.py",
                tofile="mutated-choice.py",
            )
        )
    )
    code, command = run("mutation-privacy", "all_browser_projections")
    results.append(
        {
            "name": "private-key disclosure before submission",
            "exit_code": code,
            "caught": code == 1,
            "command": command,
        }
    )
    assert code == 1, "Disclosure mutation not caught"
    SOURCE.write_bytes(original)
    bad = text.replace(
        "selected_option_id == choice.correct_option_id",
        "selected_option_id != choice.correct_option_id",
        1,
    )
    assert bad != text
    SOURCE.write_text(bad)
    invalidate_bytecode()
    (OUT / "judgment.diff").write_text(
        "".join(
            difflib.unified_diff(
                text.splitlines(keepends=True),
                bad.splitlines(keepends=True),
                fromfile="choice.py",
                tofile="mutated-choice.py",
            )
        )
    )
    code, command = run("mutation-judgment", "each_selected_option_matches_private_key")
    results.append(
        {
            "name": "program judgment disagrees with private key",
            "exit_code": code,
            "caught": code == 1,
            "command": command,
        }
    )
    assert code == 1, "Judgment mutation not caught"
finally:
    SOURCE.write_bytes(original)
    invalidate_bytecode()
    (OUT / "mutations.json").write_text(
        json.dumps(
            {
                "sha": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "results": results,
                "restored": SOURCE.read_bytes() == original,
                "source_sha256": hashlib.sha256(original).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
code, _ = run("restored-choices", None)
assert code == 0
