#!/usr/bin/env python3
"""Real model/PG/runtime pilot with official captions and a fixed Evidence boundary.

This isolates agent behavior. It does NOT test ingestion, dense retrieval, Java auth or UI.
Use a separate test database, immutable source snapshot and a new output path per cohort.
"""

import argparse
import hashlib
import json
import os
import re
import time
import urllib.request
import uuid
from pathlib import Path

from langgraph.checkpoint.postgres import PostgresSaver

import lecturelens_agent
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError, StudyStore

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "eval/study-v2"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def captions(source, path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(source["subtitle_url"], timeout=60) as response:
            path.write_bytes(response.read())
    assert digest(path.read_bytes()) == source["subtitle_sha256"], "Source changed"
    pattern = re.compile(r"(\d\d):(\d\d):(\d\d)\.(\d{3}) --> (\d\d):(\d\d):(\d\d)\.(\d{3})")
    passages = []
    current = None
    for block in path.read_text().split("\n\n"):
        match = pattern.search(block)
        if not match:
            continue
        parts = list(map(int, match.groups()))
        start = sum(a * b for a, b in zip(parts[:4], [3600000, 60000, 1000, 1], strict=True))
        end = sum(a * b for a, b in zip(parts[4:], [3600000, 60000, 1000, 1], strict=True))
        if start < source["start_ms"] or end > source["end_ms"]:
            continue
        text = " ".join(block[match.end() :].split())
        if current is None or len(current["text"]) + len(text) + 1 > 580:
            current = {
                "evidence_id": f"caption-{len(passages) + 1}",
                "text": text,
                "start_ms": start,
                "end_ms": end,
                "source_type": "SUBTITLE",
            }
            passages.append(current)
        else:
            current["text"] += " " + text
            current["end_ms"] = end
    assert 1 <= len(passages) <= 8
    return passages


class FixedEvidence:
    """All queries return the same bounded excerpt, including irrelevant-topic queries."""

    def __init__(self, scope, evidence):
        self.scope, self.evidence = scope, evidence

    def read(self, scope, action="CHECK", **arguments):
        if any(scope[k] != self.scope[k] for k in ("owner_id", "course_id", "revision")):
            raise StudyError("COURSE_UNAVAILABLE_OR_CHANGED")
        selected = []
        if action == "SEARCH":
            selected = [
                e
                for e in self.evidence
                if e["end_ms"] >= arguments.get("start_ms", 0)
                and e["start_ms"] <= arguments.get("end_ms", 10**12)
            ]
        elif action == "READ":
            selected = [e for e in self.evidence if e["evidence_id"] in arguments["evidence_ids"]]
        elif action == "WINDOW":
            index = next(
                i for i, e in enumerate(self.evidence) if e["evidence_id"] == arguments["evidence_id"]
            )
            selected = self.evidence[max(0, index - 1) : index + 2]
        return {**self.scope, "evidence": selected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    assert dsn.rsplit("/", 1)[-1] == "lecturelens_agent_test", "Use the separate test DB"
    assert not args.output.exists(), "New cohorts must never overwrite trials"
    source = json.loads((DATA / "sources.json").read_text())
    evidence = captions(source, ROOT / ".data/study-v2/lecture4.vtt")
    cases = json.loads((DATA / "cases.json").read_text())["cases"]
    package = Path(lecturelens_agent.__file__).parent
    source_hash = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        source_hash.update(str(path.relative_to(package)).encode())
        source_hash.update(path.read_bytes())
    identity = {
        "label": args.label,
        "runtime_sha256": source_hash.hexdigest(),
        "dataset_sha256": digest((DATA / "cases.json").read_bytes()),
        "source_sha256": source["subtitle_sha256"],
        "evidence_sha256": digest(json.dumps(evidence, sort_keys=True).encode()),
        "protocol": "real-model-pg-runtime-fixed-evidence-replay",
        "model": os.environ["AGENT_LLM_MODEL"],
        "deadline_seconds": 90,
    }
    store, provider = StudyStore(dsn), ChatProvider()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.umask(0o077)
    with args.output.open("x") as output:
        for case in cases:
            scope = {"owner_id": 4243, "course_id": "replay-" + uuid.uuid4().hex, "revision": 1}
            runtime = StudyRuntime(store, FixedEvidence(scope, evidence), provider, seconds=90)
            runtime.initialize()
            session = store.command(
                StudyCommand(**scope, operation="CREATE_SESSION", request_key="session"), "real"
            )["session_id"]
            scope["session_id"] = session
            run_id = store.command(
                StudyCommand(**scope, operation="START", request_key=case["id"], goal=case["goal"]), "real"
            )["run"]["run_id"]
            run = next(r for r in store.candidates() if r["run_id"] == run_id)
            start = time.monotonic()
            runtime.execute(run)
            elapsed = time.monotonic() - start
            response = store.command(StudyCommand(**scope, operation="READ"), "real")
            events = store.command(StudyCommand(**scope, operation="EVENTS"), "real")["events"]
            with store.connect() as conn:
                artifact = conn.execute(
                    "SELECT content FROM study_artifact WHERE run_id=%s", (run_id,)
                ).fetchone()
                tools = conn.execute(
                    "SELECT * FROM study_tool_result WHERE run_id=%s ORDER BY call_id", (run_id,)
                ).fetchall()
            output.write(
                json.dumps(
                    {
                        "identity": identity,
                        "case_id": case["id"],
                        "run": response["run"],
                        "elapsed_seconds": elapsed,
                        "artifact": artifact["content"] if artifact else None,
                        "evidence": evidence,
                        "events": events,
                        "tools": tools,
                    },
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
            output.flush()
            os.fsync(output.fileno())
            with PostgresSaver.from_conn_string(dsn) as saver:
                saver.delete_thread(session)
            with store.connect() as conn:
                conn.execute("DELETE FROM study_run WHERE session_id=%s", (session,))
                conn.execute("DELETE FROM study_session WHERE session_id=%s", (session,))
            print(
                json.dumps(
                    {
                        "label": args.label,
                        "case": case["id"],
                        "status": response["run"]["status"],
                        "seconds": round(elapsed, 2),
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
