"""Read immutable failures and construct requests without a provider or database."""

import argparse
import copy
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

if os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
    raise SystemExit("SOCKET_FENCE_REQUIRED")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--implementation-root", type=Path, required=True)
parser.add_argument("--archive", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
raw = args.archive.read_bytes()
if hashlib.sha256(raw).hexdigest() != "832e20a6e066603b57a858a50ddbd2eda355757ba821e4119c6056339299b30d":
    raise SystemExit("IMMUTABLE_FAILURE_ARCHIVE_CHANGED")
root = args.implementation_root.resolve()
sys.path.insert(0, str(root / "agent-service/src"))
# The chosen checkout is inserted only after the archive and socket-fence gates.
from lecturelens_real_eval.tutor.claim_grounding_runtime import LessonAuthority  # noqa: E402
from lecturelens_real_eval.tutor.relevant_authority import RelevantSnapshotAuthority  # noqa: E402
from lecturelens_real_eval.tutor.selection_runtime import IDENTITY, SelectedTutorRuntime, units  # noqa: E402

with zipfile.ZipFile(args.archive) as archive:
    assets = {name: archive.read(name) for name in archive.namelist()}
manifest = json.loads(assets["manifest.json"])
for name, expected in manifest["files"].items():
    if hashlib.sha256(assets[name]).hexdigest() != expected:
        raise SystemExit("IMMUTABLE_FAILURE_MEMBER_CHANGED")


def read(name):
    return json.loads(assets[name])


runtime_data = read("execution/runtime.json")
packet = read("original-packet.json")
snapshot = json.loads((root / "eval/tutor-v14-fresh-v1/snapshot.json").read_bytes())
canonical = LessonAuthority(snapshot).snapshot
course = packet["sessions"][0]["course_id"]
runtime = SelectedTutorRuntime.__new__(SelectedTutorRuntime)
runtime.authority = RelevantSnapshotAuthority(canonical)
session = copy.deepcopy(runtime_data["sessions"][0])
turn = copy.deepcopy(runtime_data["turns"][2])
runtime.authority.register(session, course)
history = [
    {k: t[k] for k in ("ordinal", "learner_text", "answer", "evaluation", "outcome")}
    for t in runtime_data["turns"][:2]
]
if hasattr(runtime, "history_answer"):
    for row, original in zip(history, runtime_data["turns"][:2], strict=True):
        row["answer"] = runtime.history_answer(row, original["checkpoint"])

ordinary = []
for n in (7, 8, 9):
    request = read(f"execution/wire/{n:03d}-request.body")
    original = json.loads(request["messages"][-1]["content"])
    selected = [e["evidence_id"] for e in original["evidence"]]
    observations = copy.deepcopy(original["observations"])
    for observation in observations:
        if "evidence_indices" in observation:
            observation["evidence_ids"] = [selected[i - 1] for i in observation.pop("evidence_indices")]
    state = dict(phase="ready", observations=observations, selected=selected, source_hashes={})
    messages, schemas, amount = runtime.request(session, turn, state, copy.deepcopy(history))
    ordinary.append(amount)

state = copy.deepcopy(turn["checkpoint"])
proposal = state["response"]["arguments"]
sources = {e["evidence_id"]: e["text"] for e in canonical["lectures"][course]["evidence"]}
feedback = proposal["evaluation_blocks"][0]["span"]
source = sources[feedback["evidence_id"]]
span = "".join(text for _, text in units(source)[feedback["first_unit"] - 1 : feedback["last_unit"]])
message = f"SPAN_CAPACITY: selected{len(span)} code points; limit400. Select a smaller complete supporting interval; do not omit required conditions/content."
corrected = runtime.reject(
    {**state, "selection_proposal": copy.deepcopy(proposal), "structured_proposal": copy.deepcopy(proposal)},
    "finish_tutor_turn",
    "TUTOR_FINISH_REPAIR_REQUIRED",
    message,
)
_, _, repair = runtime.request(session, turn, corrected, copy.deepcopy(history))

outcomes = read("execution/outcomes.json")
result = {
    "kind": "HISTORICAL_FAILURE_AND_REQUEST_CONSTRUCTION_ONLY",
    "real_model_quality": "NOT_RUN",
    "new_provider_requests": 0,
    "database_connections": 0,
    "identity": IDENTITY,
    "implementation_source_sha256": hashlib.sha256(
        (root / "agent-service/src/lecturelens_real_eval/tutor/selection_runtime.py").read_bytes()
    ).hexdigest(),
    "archive_sha256": hashlib.sha256(raw).hexdigest(),
    "original_summary": read("execution/summary.json"),
    "first_turn_original_block_kinds": [
        b["kind"]
        for b in json.loads(
            read("execution/wire/003-response.body")["choices"][0]["message"]["tool_calls"][0]["function"][
                "arguments"
            ]
        )["blocks"]
    ],
    "second_turn_original_hint_intent": json.loads(
        read("execution/wire/006-response.body")["choices"][0]["message"]["tool_calls"][0]["function"][
            "arguments"
        ]
    )["hint"]["intent"],
    "second_turn_repair_observations": [
        o
        for o in json.loads(read("execution/wire/006-request.body")["messages"][-1]["content"])[
            "observations"
        ]
        if o.get("error")
    ],
    "earlier_learner_text_preserved": history[0]["learner_text"] == packet["sessions"][0]["turns"][0]["text"],
    "original_source_only_answer_codepoints": len(outcomes[0]["answer"]),
    "current_history_answer_codepoints": len(history[0]["answer"]),
    "ordinary_request_proxies": ordinary,
    "ordinary_proxy_total": sum(ordinary),
    "repair_request_proxy": repair,
    "total_with_repair": sum(ordinary) + repair,
    "original_committed_turn_proxy": turn["reserved_tokens"],
    "unchanged_turn_proxy_cap": 64000,
    "would_fit_repair": sum(ordinary) + repair <= 64000,
    "first_feedback_anchor_codepoints": len(span),
    "unchanged_feedback_anchor_cap": 400,
    "historical_failure_relabelled": False,
}
args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open("x") as file:
    json.dump(result, file, ensure_ascii=False, indent=2)
print(
    json.dumps(
        {
            k: result[k]
            for k in (
                "identity",
                "ordinary_proxy_total",
                "repair_request_proxy",
                "total_with_repair",
                "would_fit_repair",
                "new_provider_requests",
            )
        }
    )
)
