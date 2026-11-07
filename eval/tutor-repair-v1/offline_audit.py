"""Replay retained parsed decisions, not unavailable raw provider bodies; never sends."""

# ruff: noqa: E402 -- local versioned eval imports require explicit paths

import argparse
import hashlib
import json
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-python-contract-v1"))
import contract_check as parent
from lecturelens_real_eval.runner import SnapshotAuthority
from lecturelens_real_eval.tutor.grounded_runtime import PassageAuthority
from lecturelens_real_eval.tutor.observed_channel import (
    DecodedMetadataTransport,
    ObservedChannel,
)
from lecturelens_real_eval.tutor_channel import TutorPolicy
from public_dataset import digest, read, write


class MemoryLedger:
    """Explicit Mock arithmetic sink, never a substitute for persistent paid accounting."""

    policy = TutorPolicy()

    def __init__(self):
        self.rows = []

    def reserve(self, raw, max_tokens):
        return {"call_id": f"MOCK-{len(self.rows)}", "reserved_nano_usd": None}

    def settle(self, reservation, usage, error):
        self.rows.append({"usage": usage, "error": error})


def audit(output):
    output.mkdir(exist_ok=False, parents=True)
    _, scripts, snapshot = parent.load_plan(ROOT / "eval/tutor-python-contract-v1/development-pilot-v1.json")
    run = ROOT / ".data/tutor-pilot-v1/first-real-20261107"
    raw = ROOT / ".data/tutor-first-live-20261107"
    turns = [json.loads(line) for line in (run / "turns.jsonl").read_text().splitlines()]
    pg = read(raw / "postgres-run-snapshot.json")
    original, derived = SnapshotAuthority(snapshot), PassageAuthority(snapshot)
    comparisons, replay, number = [], [], 0
    for turn, script in zip(turns, [d for d in scripts for _ in d["turns"]], strict=True):
        persisted = next(t for t in pg["turns"] if t["learner_text"] == turn["script"]["text"])
        assert persisted["answer"] == turn["answer"]
        observed = [
            o for o in persisted["checkpoint"]["observations"] if o["tool"] == "search_tutor_evidence"
        ]
        search_number = 0
        scope = dict(owner_id=811012, course_id=script["course_id"], revision=1)
        original.register(scope, script["lecture_id"])
        derived.register(scope, script["lecture_id"])
        proposals = iter(turn["proposals"])
        for call in turn["calls"]:
            number += 1
            first = next(proposals)
            # The frozen provider retained every parallel proposal; only the first was executed.
            group = [first] + [next(proposals) for _ in range(first["dropped_tool_calls"])]
            assert all(p["usage"] == first["usage"] for p in group)
            assert first["usage"] == {k: call[k] for k in ("prompt_tokens", "completion_tokens")}
            payload = read(raw / f"wire/{number:03}-request.json")
            frame = read(raw / f"wire/{number:03}-response.json")
            # No invented model/cache/IDs. These synthetic envelopes contain only retained values.
            data = {
                "usage": first["usage"],
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {"name": p["name"], "arguments": json.dumps(p["arguments"])},
                                }
                                for p in group
                            ]
                        },
                    }
                ],
            }
            ledger = MemoryLedger()
            channel = ObservedChannel(
                ledger,
                records=output / "replayed-calls.jsonl",
                transport=DecodedMetadataTransport(
                    httpx.MockTransport(lambda request, data=data: httpx.Response(200, json=data))
                ),
            )
            channel.turn_key = turn["turn_key"]
            result = channel.request(payload["messages"], payload["tools"])
            assert result == first
            assert channel.turn_calls[0]["returned_model"] is None
            assert channel.turn_calls[0]["cache"]["status"] == "UNKNOWN"
            replay.append(
                dict(
                    turn_key=turn["turn_key"],
                    request=number,
                    request_sha256=digest(raw / f"wire/{number:03}-request.json"),
                    retained_response_frame_sha256=digest(raw / f"wire/{number:03}-response.json"),
                    original_frame_fields=list(frame),
                    parsed_decision_equal=True,
                )
            )
            if first["name"] == "search_tutor_evidence":
                query = first["arguments"]["query"]
                before = original.read(scope, "SEARCH", query=query)["evidence"]
                assert observed[search_number]["query"] == query
                assert observed[search_number]["evidence_ids"] == [e["evidence_id"] for e in before]
                search_number += 1
                after = derived.read(scope, "SEARCH", query=query)["evidence"]
                by_id = {e["evidence_id"]: e for e in derived.rows(scope)}
                comparisons.append(
                    dict(
                        turn_key=turn["turn_key"],
                        query=query,
                        before_ids=[e["evidence_id"] for e in before],
                        after_passages=[
                            {
                                k: by_id[e["evidence_id"]][k]
                                for k in ("evidence_id", "line_start", "line_end", "member_evidence_ids")
                            }
                            for e in after
                        ],
                    )
                )
        assert next(proposals, None) is None
        assert search_number == len(observed)
    assert number == 20
    report = dict(
        kind="OFFLINE_MOCK_RECONSTRUCTED_PARSED_RESPONSE_REPLAY",
        requests=number,
        turns=len(turns),
        original_answers_sha256=[hashlib.sha256(t["answer"].encode()).hexdigest() for t in turns],
        original_answers_changed=False,
        original_wrong_index_still_present="data[30, 20]" in turns[2]["answer"],
        raw_provider_response_bodies="UNAVAILABLE_NOT_RECONSTRUCTED",
        historic_returned_model="UNKNOWN_CAPTURE_FAILED",
        historic_cache="UNKNOWN_CAPTURE_FAILED",
        post_fix_real_quality="NOT_RUN",
        real_cost="NOT_RUN",
        requests_replayed=replay,
        retrieval_comparisons=comparisons,
        baseline_pg_answers_and_search_observations_equal=True,
    )
    write(output / "audit.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.output)
    print(json.dumps({k: result[k] for k in ("kind", "requests", "turns", "post_fix_real_quality")}))
