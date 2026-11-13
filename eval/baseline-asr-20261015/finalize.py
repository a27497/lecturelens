"""Finalize only a fully observed batch; no service writes or model calls."""

import datetime
import hashlib
import json
import subprocess
import sys

from score import REPORT, ROOT, records


def save(path, value):
    with path.open("x") as stream:
        stream.write(value)


def run(command, name, input_text=None):
    started = datetime.datetime.now(datetime.UTC).isoformat()
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, input=input_text, check=False
    )
    record = {
        "command": command,
        "started_at_utc": started,
        "finished_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    save(REPORT / "checks" / f"{name}.json", json.dumps(record, indent=2) + "\n")
    print(name, result.returncode, flush=True)
    if result.returncode:
        raise RuntimeError(f"{name} failed; see checks/{name}.json")
    return result.stdout


def main():
    batch = REPORT / "batch-v2"
    rows = records(batch / "trials.jsonl")
    finished = [r for r in rows if r["phase"] == "finished"]
    assert len(finished) == 10 and len(rows) == 20, "Batch is not complete"
    task_ids = {r["task_id"] for r in finished}
    assert len(task_ids) == 10
    assert not (REPORT / "summary.json").exists(), "Refuse overwriting a report"
    identity = json.loads((REPORT / "score-identity-final.json").read_text())
    assert (
        hashlib.sha256((REPORT / "score.py").read_bytes()).hexdigest()
        == identity["score_sha256"]
    )
    (REPORT / "checks").mkdir(exist_ok=True)
    # Retain the original timing lines so the projection itself is auditable.
    log = ROOT / ".data/baseline-asr-20261015/backend-v2.log"
    selected = "\n".join(
        line
        for line in log.read_text().splitlines()
        if any(task_id in line for task_id in task_ids)
        and any(
            marker in line
            for marker in (
                "event=pipeline_step_",
                "ASR chunk failed, retrying:",
                "event=llm_aligned_batch_translation_",
                "event=llm_aligned_batch_semantic_retry",
            )
        )
    )
    save(batch / "pipeline-log.txt", selected + "\n")
    delivery = "\n".join(
        line
        for line in log.read_text().splitlines()
        if any(task_id in line for task_id in task_ids)
        and any(
            marker in line
            for marker in (
                "event=mq_message_send_requested ",
                "event=mq_message_send_failed ",
                "event=mq_message_send_completed ",
                "event=outbox_delivery_failed ",
            )
        )
    )
    save(batch / "delivery-log.txt", delivery + "\n")
    command = [
        sys.executable,
        str(REPORT / "collect-stages.py"),
        "--log",
        str(batch / "pipeline-log.txt"),
        "--trials",
        str(batch / "trials.jsonl"),
    ]
    save(batch / "pipeline-events.jsonl", run(command, "stage-projection"))
    index_lines = [
        line
        for line in (REPORT / "http-calls.jsonl").read_text().splitlines()
        if (row := json.loads(line))["kind"] == "index"
        and row.get("course_id") in task_ids
    ]
    save(
        batch / "index-http-calls.jsonl",
        "\n".join(index_lines) + ("\n" if index_lines else ""),
    )
    run(
        [
            sys.executable,
            str(REPORT / "score.py"),
            "--output",
            str(REPORT / "summary.json"),
        ],
        "score",
    )
    save(
        REPORT / "cost-audit.json",
        run([sys.executable, str(REPORT / "cost-audit.py")], "cost-audit"),
    )
    save(
        REPORT / "coverage-asr.json",
        run([sys.executable, str(REPORT / "coverage_asr.py")], "coverage-asr"),
    )
    save(
        REPORT / "delivery-audit.json",
        run([sys.executable, str(REPORT / "delivery-audit.py")], "delivery-audit"),
    )
    save(
        REPORT / "README.md",
        run([sys.executable, str(REPORT / "render-report.py")], "render-report"),
    )
    run([sys.executable, str(REPORT / "verify.py")], "recompute")
    output = run([sys.executable, str(REPORT / "score.py")], "byte-recompute")
    assert output == (REPORT / "summary.json").read_text(), "Byte mismatch"
    run(["cmp", "-", str(REPORT / "summary.json")], "byte-comparison", output)
    run([sys.executable, str(REPORT / "prepare.py")], "asset-hashes")
    run([sys.executable, str(REPORT / "verify-media.py")], "media-packets")
    run(
        [
            sys.executable,
            str(REPORT / "start-direct.py"),
            "--check-only",
            "--source-pid",
            "5104",
            "--jar",
            "/home/dev/projects/lecturelens-asr-b/.data/asr-b-deploy/backend-asr-b.jar",
            "--asr-config",
            "/home/dev/projects/lecturelens-asr-b/.data/asr-b-deploy/asr-bailian.yml",
            "--batch",
            str(batch),
        ],
        "startup-preflight",
    )
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(REPORT / "test_score.py"),
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={REPORT / 'checks/mechanism-final.xml'}",
        ],
        "mechanism-tests",
    )
    ruff = str(ROOT / "agent-service/.venv/bin/ruff")
    run([ruff, "check", "agent-service", str(REPORT)], "ruff")
    run([ruff, "format", "--check", str(REPORT)], "ruff-format")
    run(["git", "diff", "--name-only"], "tracked-file-diff")
    print("Summary, report and measured checks ready; finish VERIFY and SHA256SUMS.")


if __name__ == "__main__":
    main()
