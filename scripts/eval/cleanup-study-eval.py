#!/usr/bin/env python3
"""Delete only courses created by this local evaluation and verify asynchronous cleanup."""

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".data/l22-eval"


def api(base, path, body=None, token=None, expected=200):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": "Bearer " + token} if token else {}),
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        assert response.status == expected, (path, response.status)
        return json.loads(response.read()).get("data")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--sources-manifest", type=Path)
    args = parser.parse_args()
    output, base = args.output, args.base_url.rstrip("/")
    env = json.loads((output / "runtime.local.json").read_text())
    source = json.loads((args.sources_manifest or output / "sources/clips.json").read_text())
    clips = {clip["id"]: clip["sha256"] for clip in (source["clips"] if isinstance(source, dict) else source)}
    courses, owners = [], []
    for clip, digest in clips.items():
        auth = json.loads((output / "courses" / clip / "session.local.json").read_text())
        assert auth.get("base_url", "http://127.0.0.1:8080") == base, "Course belongs to another API endpoint"
        assert auth["video_sha256"] == digest
        assert auth["credentials"]["email"].startswith("l2-") and auth["credentials"]["email"].endswith(
            "@example.com"
        )
        ids = [auth["task_id"], *auth.get("failed_task_ids", [])]
        courses.extend(ids)
        owners.append((auth, ids))
    with psycopg.connect(env["AGENT_DATABASE_URL"]) as conn:
        sessions = [
            row[0]
            for row in conn.execute(
                "SELECT session_id FROM study_session WHERE course_id=ANY(%s)", (courses,)
            )
        ]
        runs = [
            row[0]
            for row in conn.execute("SELECT run_id FROM study_run WHERE session_id=ANY(%s)", (sessions,))
        ]
        assert (
            conn.execute(
                "SELECT count(*) FROM study_run WHERE run_id=ANY(%s) AND status IN ('queued','running')",
                (runs,),
            ).fetchone()[0]
            == 0
        )
    # Keep scoped IDs to permit verification after an interrupted deletion.
    scope_path = output / "cleanup-scope.local.json"
    prior = json.loads(scope_path.read_text()) if scope_path.exists() else {"sessions": [], "runs": []}
    sessions = list(set(sessions + prior["sessions"]))
    runs = list(set(runs + prior["runs"]))
    scope_path.write_text(json.dumps({"sessions": sessions, "runs": runs}))
    scope_path.chmod(0o600)
    for auth, ids in owners:
        token = api(base, "/api/auth/login", auth["credentials"])["accessToken"]
        deleted = api(base, "/api/tasks/batch-delete", {"taskIds": ids}, token)
        assert 0 <= deleted["deletedCount"] <= len(ids)
        for task in ids:
            api(base, f"/api/tasks/{task}/evidence/index-status", token=token, expected=404)
        api(base, f"/api/tasks/{auth['task_id']}/study/command", {"operation": "LIST"}, token, expected=404)
    deadline = time.monotonic() + 120
    while True:
        with psycopg.connect(env["AGENT_DATABASE_URL"]) as conn:
            counts = {}
            for table, column, values in [
                ("indexed_evidence", "course_id", courses),
                ("evidence_vector", "course_id", courses),
                ("study_session", "session_id", sessions),
                ("study_run", "run_id", runs),
                ("study_artifact", "run_id", runs),
                ("study_tool_result", "run_id", runs),
                ("study_event", "run_id", runs),
                ("checkpoints", "thread_id", sessions),
                ("checkpoint_blobs", "thread_id", sessions),
                ("checkpoint_writes", "thread_id", sessions),
            ]:
                counts[table] = conn.execute(
                    sql.SQL("SELECT count(*) FROM {} WHERE {}=ANY(%s)").format(
                        sql.Identifier(table), sql.Identifier(column)
                    ),
                    (values,),
                ).fetchone()[0]
            tombstones = conn.execute(
                "SELECT count(*) FROM evidence_index WHERE course_id=ANY(%s) AND state='DELETED'", (courses,)
            ).fetchone()[0]
        if not any(counts.values()) and tombstones == len(courses):
            break
        assert time.monotonic() < deadline, (counts, tombstones)
        time.sleep(2)
    report = {
        "owned_courses_deleted": len(courses),
        "sessions_before": len(sessions),
        "runs_before": len(runs),
        "immediate_http_404": True,
        "tombstones": tombstones,
        "remaining_rows": counts,
    }
    (output / "cleanup-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
