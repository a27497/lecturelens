"""V15 consumed-development end-to-end replayable Mock trial; no live switch."""

import argparse
import json
import os
import uuid
from pathlib import Path

import httpx
import psycopg
from check_tutor_phase_identity import ROOT, verify
from lecturelens_real_eval.tutor.bounded_mock import SourcePreservingMock
from lecturelens_real_eval.tutor.bounded_provider import BoundedTutorProvider
from lecturelens_real_eval.tutor.bounded_runtime import BoundedTutorRuntime
from lecturelens_real_eval.tutor.bounded_store import BoundedStore
from lecturelens_real_eval.tutor.claim_grounding_runtime import LessonAuthority
from lecturelens_real_eval.tutor.contracts import Command
from lecturelens_real_eval.tutor.observed_channel import DecodedMetadataTransport, ObservedChannel
from lecturelens_real_eval.tutor.relevant_authority import RelevantSnapshotAuthority
from lecturelens_real_eval.tutor_channel import Ledger, TutorPolicy
from psycopg import sql
from psycopg.conninfo import make_conninfo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    candidate = verify()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "wire").mkdir()
    dsn = "postgresql://tutor_scale:synthetic-local-only@127.0.0.1:25841/lecturelens_agent_acceptance"
    schema = "v15_packet_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    isolated = make_conninfo(dsn, options=f"-csearch_path={schema},public")
    mock, sent, outcomes = SourcePreservingMock(), [], []

    def send(request):
        sent.append(1)
        (output / "wire" / f"{len(sent):03d}.json").write_bytes(request.content)
        wire = json.loads(request.content)
        response = mock.decide(wire["messages"], wire["tools"], 20)
        return httpx.Response(
            200,
            json={
                "id": "mock-" + str(len(sent)),
                "model": "deepseek-flash",
                "usage": {"prompt_tokens": 100, "completion_tokens": 60},
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": response["name"],
                                        "arguments": json.dumps(response["arguments"]),
                                    },
                                }
                            ]
                        },
                    }
                ],
            },
        )

    try:
        snapshot = json.loads((ROOT / "eval/tutor-v14-fresh-v1/snapshot.json").read_text())
        authority = RelevantSnapshotAuthority(LessonAuthority(snapshot).snapshot)
        ledger = Ledger(
            isolated,
            output / "ledger.jsonl",
            "v15-development-mock",
            TutorPolicy(max_calls=80, candidate_sha256=candidate),
        )
        ledger.install()
        channel = ObservedChannel(
            ledger,
            records=output / "calls.jsonl",
            transport=DecodedMetadataTransport(httpx.MockTransport(send)),
        )
        provider = BoundedTutorProvider(channel, authority)
        runtime = BoundedTutorRuntime(BoundedStore(isolated), authority, provider)
        runtime.initialize()
        original = json.loads((ROOT / "eval/tutor-v14-fresh-v1/development.json").read_text())["dialogues"]
        contract = json.loads((ROOT / "eval/tutor-repair-phase-v1/contract-v2.json").read_text())
        for dialogue in original:
            scope = dict(owner_id=811015, course_id="mock-" + dialogue["dialogue_id"], revision=1)
            authority.register(scope, dialogue["lecture_id"])
            scope["session_id"] = runtime.command(Command(**scope, operation="CREATE", request_key="s"))[
                "session"
            ]["session_id"]
            provider.scope = scope
            closed = False
            for ordinal, task in enumerate(dialogue["turns"], 1):
                key = f"{dialogue['dialogue_id']}:{ordinal}"
                if closed:
                    outcomes.append(dict(turn_key=key, status="SKIPPED", reason="SESSION_CLOSED"))
                    continue
                channel.turn_key, channel.turn_calls, provider.proposals = key, [], []
                runtime.command(
                    Command(
                        **scope,
                        operation="TURN",
                        client_turn_id=f"t{ordinal}",
                        text=contract["tasks"][key]["text"],
                        socratic=task["socratic"],
                    )
                )
                runtime.execute(runtime.store.candidates()[0])
                row = runtime.command(Command(**scope, operation="GET"))["turns"][-1]
                outcomes.append(dict(turn_key=key, **row))
                closed = row["status"] != "completed"
        summary = dict(
            candidate_sha256=candidate,
            expected=16,
            completed=sum(r["status"] == "completed" for r in outcomes),
            failed=sum(r["status"] == "failed" for r in outcomes),
            skipped=sum(r["status"] == "SKIPPED" for r in outcomes),
            requests=len(sent),
            ledger=ledger.check(),
            usage_kind="SIMULATED_NOT_NEW_CHARGES",
            quality="NOT_RUN",
            real_model_calls=0,
            embedding_calls=0,
            reviewer_calls=0,
            cost_usd="0",
        )
        (output / "outcomes.json").write_text(json.dumps(outcomes, indent=2, default=str) + "\n")
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        runtime.close()
        print(json.dumps(summary))
        assert len(outcomes) == 16 and summary["completed"] == 16
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    main()
