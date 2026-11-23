"""Replay the approved Chinese Light Tutor development packet over signed Evidence."""

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import uvicorn
from fastapi.testclient import TestClient
from lecturelens_agent.app import create_app as vector_app
from lecturelens_agent.contracts import Evidence, EvidenceMetadata, SyncRequest
from lecturelens_agent.retrieval import split_evidence
from lecturelens_agent.study.authority import EvidenceAuthority
from lecturelens_agent.study.store import StudyError
from lecturelens_real_eval.tutor.app import create_app as tutor_app
from lecturelens_real_eval.tutor.flash_provider import PRODUCT_TEXT_SYSTEM
from lecturelens_real_eval.tutor.light import SYSTEM
from lecturelens_real_eval.tutor.light_retrieval import MAX_CONTEXT, MAX_QUERIES
from lecturelens_real_eval.tutor.query_language import _chinese
from tutor_retrieval_dev import (
    isolated_retriever,
    measure,
    sha256,
    summary,
    write_private,
)
from tutor_selective_neighbors import (
    LockedVector,
    check_vector_receipts,
    expected_snapshots,
)

BASE = "b02ca48981a4d60589ac92463c53d5d04fb9df96"
PLAN = "295dab4698130a2ae89c7747397b009a1e3ad2576585a48c09a93e2ac2637d43"
REVIEW = "3ce4521a7e72ed273b9870ddff73db4cb4dbbc10d0a5b57a083732e2c73e7985"
ARMS = ("original", "english", "bilingual")
GUARDED = ("comparison_within_lecture", "cross_segment_two_timestamps_5min_apart")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(root, name):
    return json.loads((root / name).read_bytes())


def reviewed(root):
    plan_path = root.parent / "PREREGISTRATION-2026-11-23.md"
    if digest(root / "review-receipt.json") != REVIEW or digest(plan_path) != PLAN:
        raise ValueError("Unexpected study preregistration or review identity")
    receipt = load(root, "review-receipt.json")
    if receipt["decision"] != "APPROVED":
        raise ValueError("Replay requires exact independent review approval")
    for name, descriptor in receipt["verified_inputs"].items():
        if digest(root / name) != descriptor["sha256"]:
            raise ValueError("Approved study input changed")

    items = load(root, "packet.json")
    support = load(root, "support.json")
    snapshots = load(root, "original-english-evidence.json")
    scopes = {
        lecture: {
            "owner_id": source["owner_id"],
            "course_id": source["task_id"],
            "revision": source["revision"],
        }
        for lecture, source in snapshots.items()
    }
    manifest = load(root, "inputs.json")
    for prompt, name in ((SYSTEM, "light"), (PRODUCT_TEXT_SYSTEM, "trial")):
        if (
            hashlib.sha256(prompt.encode()).hexdigest()
            != manifest[f"{name}_system_sha256"]
        ):
            raise ValueError("Product prompt changed")
    if len(items) != 42 or len({row["item_id"] for row in items}) != 42:
        raise ValueError("Unexpected development sample")
    if set(support) != {row["item_id"] for row in items if row["answerable"]}:
        raise ValueError("Refusals and supported items disagree with approved manifest")
    for row in items:
        known = {e["evidenceId"] for e in snapshots[row["lecture_id"]]["items"]}
        vital = support.get(row["item_id"], {})
        if set(vital) != set(row.get("vital_ids", ())):
            raise ValueError("Reviewed vital labels differ")
        for alternatives in vital.values():
            if not alternatives or any(
                not group or set(group) - known for group in alternatives
            ):
                raise ValueError("Invalid reviewed alternative")

    return items, support, snapshots, scopes


def seed(snapshots, scopes, fixture):
    retriever = isolated_retriever()
    retriever.store.initialize()
    chunks = []
    for lecture, snap in snapshots.items():
        scope = scopes[lecture]
        rows = []
        for e in snap["items"]:
            if (e["ownerId"], e["courseId"], e["revision"]) != tuple(
                scope.values()
            ) or not (
                e["retrievable"]
                and e["sourceType"] == "SUBTITLE"
                and e["language"] == "en"
            ):
                raise ValueError(
                    "Wrong scope or language in the English source projection"
                )
            rows.append(
                Evidence(
                    evidence_id=e["evidenceId"],
                    text=e["normalizedText"],
                    start_ms=e["startMs"],
                    end_ms=e["endMs"],
                )
            )
        reply = retriever.sync(
            SyncRequest(
                request_id="tutor-zh-en-dev",
                **scope,
                sequence=1,
                operation="APPLY",
                index_version=retriever.embedder.index_version,
                upserts=rows,
                manifest=[
                    EvidenceMetadata(
                        evidence_id=e.evidence_id,
                        start_ms=e.start_ms,
                        end_ms=e.end_ms,
                        content_hash=hashlib.sha256(e.text.encode()).hexdigest(),
                    )
                    for e in rows
                ],
            )
        )
        if reply["state"] != "READY":
            raise ValueError("Projection is unavailable")
        chunks.extend(
            (row.evidence_id, hashlib.sha256(chunk.encode()).hexdigest())
            for row, chunk in split_evidence(rows)
        )
    write_private(fixture, list(snapshots.values()))
    print(
        json.dumps(
            {
                "excerpts": sum(len(s["items"]) for s in snapshots.values()),
                "chunks": len(chunks),
                "chunk_manifest_sha256": sha256(chunks),
                "index": retriever.embedder.index_version,
            }
        )
    )


def baseline_runtime(authority, provider):
    loaded = {}
    for name in ("light_retrieval", "light"):
        module = ModuleType(f"lecturelens_real_eval.tutor._replay_base_{name}")
        path = f"agent-service/src/lecturelens_real_eval/tutor/{name}.py"
        source = subprocess.check_output(["git", "show", f"{BASE}:{path}"])
        # Only the literal base commit and the two fixed repository paths can supply source.
        exec(compile(source, f"{BASE}:{path}", "exec"), module.__dict__)  # noqa: S102
        loaded[name] = module
    loaded["light"].retrieve_context = loaded["light_retrieval"].retrieve_context
    return loaded["light"].LightTutorRuntime(
        SimpleNamespace(engine="light"), authority, provider
    )


def stats(values):
    return {
        "mean": round(statistics.mean(values), 2),
        "p95": round(sorted(values)[math.ceil(len(values) * 0.95) - 1], 2),
        "max": round(max(values), 2),
    }


def slices(item):
    if item["answerable"]:
        return ("all", item["language"], f"{item['language']}/{item['category']}")
    return ("all", "refusals", f"{item['language']}/refusal")


def report(results):
    paired = {}
    for arm, rows in results.items():
        groups, gains = {}, {}
        for item_id, row in rows.items():
            baseline = results["original"][item_id]
            for key in slices(row):
                groups.setdefault(key, []).append(row)
                gains.setdefault(key, []).append((baseline, row))
        paired[arm] = {}
        for group, rows in groups.items():
            cases = gains[group]
            full_gain = full_loss = vital_gain = vital_loss = 0
            for before, after in cases:
                if before["answerable"]:
                    full_gain += not all(before["nuggets"].values()) and all(
                        after["nuggets"].values()
                    )
                    full_loss += all(before["nuggets"].values()) and not all(
                        after["nuggets"].values()
                    )
                    for nid in before["nuggets"]:
                        vital_gain += (
                            not before["nuggets"][nid] and after["nuggets"][nid]
                        )
                        vital_loss += (
                            before["nuggets"][nid] and not after["nuggets"][nid]
                        )
            paired[arm][group] = summary(rows) | {
                "full_gain_loss": [full_gain, full_loss],
                "vital_gain_loss": [vital_gain, vital_loss],
                "elapsed_ms": stats([row["elapsed_ms"] for row in rows]),
                "paired_elapsed_increment_ms": stats(
                    [
                        after["elapsed_ms"] - before["elapsed_ms"]
                        for before, after in cases
                    ]
                ),
                "ordered_evidence_changed": sum(
                    before["evidence_sha256"] != after["evidence_sha256"]
                    for before, after in cases
                ),
                "query_plan_changed": sum(
                    before["query_sha256"] != after["query_sha256"]
                    for before, after in cases
                ),
                "fallbacks": sum(row["fallback"] for row in rows),
                "nonempty_contexts": sum(bool(row["chunks"]) for row in rows),
            }
    return paired


def choose(result):
    base = result["original"]
    gates = {}
    for mode in ARMS[1:]:
        row = result[mode]
        gates[mode] = {
            "chinese_full": row["zh"]["full"][0] >= base["zh"]["full"][0] + 2,
            "chinese_micro": row["zh"]["vital"][0] > base["zh"]["vital"][0],
            "comparison_cross_segment": all(
                row[f"zh/{key}"][metric][0] >= base[f"zh/{key}"][metric][0]
                for key in GUARDED
                for metric in ("full", "vital")
            ),
            "english_identical": all(
                row[key]["ordered_evidence_changed"]
                == row[key]["query_plan_changed"]
                == 0
                for key in ("en", "en/refusal")
            ),
            "context": row["all"]["chunks"]["max"] <= MAX_CONTEXT
            and all(
                row["all"]["context_bytes"][metric]
                <= base["all"]["context_bytes"][metric] * 1.1
                for metric in ("mean", "p95")
            ),
            "latency": row["zh"]["elapsed_ms"]["p95"] <= 2000
            and row["zh"]["paired_elapsed_increment_ms"]["p95"] <= 1750,
        }
    passing = [mode for mode in ARMS[1:] if all(gates[mode].values())]
    selected = min(
        passing,
        key=lambda mode: (
            -result[mode]["zh"]["full"][0],
            -result[mode]["zh"]["vital"][0],
            result[mode]["zh"]["elapsed_ms"]["p95"],
            ARMS.index(mode),
        ),
        default=None,
    )
    return selected, gates


class GenerationForbidden:
    def __init__(self):
        self.calls = 0

    def complete(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("Retrieval-only replay forbids generation")


def permission_checks(authority, scopes, snapshots, port):
    first, second, *_ = scopes.values()
    foreign = next(
        s["items"][0]["evidenceId"]
        for key, s in snapshots.items()
        if scopes[key] == second
    )
    for client, scope, action, kwargs in (
        (
            authority,
            first | {"owner_id": first["owner_id"] + 1},
            "TUTOR_SEARCH",
            {"query": "course", "tutor_strategy": "HYBRID_8"},
        ),
        (
            authority,
            first | {"revision": first["revision"] + 1},
            "TUTOR_SEARCH",
            {"query": "course", "tutor_strategy": "HYBRID_8"},
        ),
        (authority, first, "READ", {"evidence_ids": [foreign]}),
        (
            EvidenceAuthority(f"http://127.0.0.1:{port}", "bad-signature"),
            first,
            "CHECK",
            {},
        ),
    ):
        try:
            client.read(scope, action, **kwargs)
        except StudyError as error:
            if error.code == "COURSE_UNAVAILABLE_OR_CHANGED":
                continue
            raise
        raise ValueError("Signed authority accepted an unauthorized request")


def replay(items, support, snapshots, scopes, args):
    secret = os.environ["TUTOR_DEV_SIGNING_KEY"]
    java = f"http://127.0.0.1:{args.port}"
    authority = EvidenceAuthority(java, secret)
    provider = GenerationForbidden()
    base = baseline_runtime(authority, provider)
    expected = expected_snapshots(snapshots, scopes)
    settings = {
        "TUTOR_ENABLED": "true",
        "TUTOR_ENGINE": "light",
        "TUTOR_PROVIDER": "mock",
        "AGENT_LLM_MODE": "mock",
        "STUDY_AGENT_ENABLED": "false",
        "AGENT_COURSE_TOOL_TRANSPORT": "internal",
        "AGENT_JAVA_BASE_URL": java,
        "AGENT_DATABASE_URL": os.environ["AGENT_TEST_DATABASE_URL"],
    }
    result = {arm: {} for arm in ARMS}
    with ExitStack() as stack:
        runtimes = {}
        for arm in ARMS:
            with patch.dict(os.environ, settings | {"TUTOR_QUERY_LANGUAGE": arm}):
                app = tutor_app(retriever=SimpleNamespace(), secret=secret)
                stack.enter_context(TestClient(app))
            runtimes[arm] = app.state.tutor
            runtimes[arm].provider = provider
        # Warm the Java and vector stacks with a synthetic question and check authority fences.
        authority.read(
            next(iter(scopes.values())),
            "TUTOR_SEARCH",
            query="Transcript example",
            tutor_strategy="HYBRID_8",
        )
        permission_checks(authority, scopes, snapshots, args.port)
        vector = stack.enter_context(args.vector_receipts.open())
        vector.seek(0, os.SEEK_END)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        private = stack.enter_context(os.fdopen(fd, "w"))
        for index, item in enumerate(items):
            scope = scopes[item["lecture_id"]]
            known = {e["evidenceId"]: e for e in snapshots[item["lecture_id"]]["items"]}
            turn = {"learner_text": item["question"], "socratic": False}
            states = {}
            elapsed = {}
            offset = index % len(ARMS)
            for arm in (*ARMS[offset:], *ARMS[:offset]):
                runtime = base if arm == "original" else runtimes[arm]
                started = time.monotonic_ns()
                state = runtime.prepare(scope, turn, [])
                elapsed[arm] = (time.monotonic_ns() - started) / 1e6
                states[arm] = state
                count = len(state["searches"])
                if not 1 <= count <= MAX_QUERIES:
                    raise ValueError("Search count beyond existing Tutor plan")
                snapshot_id = check_vector_receipts(vector, scope, expected, count)
                private.write(
                    json.dumps(
                        {
                            "arm": arm,
                            "item_id": item["item_id"],
                            "elapsed_ms": elapsed[arm],
                            "snapshot_id": snapshot_id,
                            "evidence": state["evidence"],
                            "searches": state["searches"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                private.flush()
            current = runtimes["original"].prepare(scope, turn, [])
            if current != states["original"]:
                raise ValueError("Disabled candidate differs from pinned baseline")
            check_vector_receipts(vector, scope, expected, len(current["searches"]))
            original_queries = [row["query"] for row in states["original"]["searches"]]
            for arm, state in states.items():
                data = json.loads(state["messages"][-1]["content"])
                evidence, queries = (
                    data["current_evidence"],
                    [row["query"] for row in state["searches"]],
                )
                if (
                    data["learner_question"] != item["question"]
                    or data["dialogue"] != []
                    or state["messages"][0] != current["messages"][0]
                    or state["schema"] != current["schema"]
                ):
                    raise ValueError("Learner wording or generation contract changed")
                if len(queries) != len(original_queries) or len(evidence) > MAX_CONTEXT:
                    raise ValueError("Final Evidence or route budget changed")
                for e in evidence:
                    original = known[e["evidence_id"]]
                    if (e["text"], e["start_ms"], e["end_ms"], e["source_type"]) != (
                        original["normalizedText"][:1200],
                        original["startMs"],
                        original["endMs"],
                        "SUBTITLE",
                    ):
                        raise ValueError("Final READ does not match approved source")
                row = measure(item, evidence, support, len(queries)) | {
                    "language": item["language"],
                    "elapsed_ms": elapsed[arm],
                    "query_sha256": sha256(queries),
                    "evidence_sha256": sha256(evidence),
                    "fallback": arm != "original"
                    and _chinese(item["question"])
                    and queries == original_queries,
                }
                result[arm][item["item_id"]] = row
        if provider.calls:
            raise ValueError("Unexpected Tutor provider calls")
    write_private(args.output.with_suffix(".scores.json"), result)
    aggregates = report(result)
    selected, gates = choose(aggregates)
    print(
        json.dumps(
            {
                "base": BASE,
                "review_sha256": REVIEW,
                "turns": len(items) * len(ARMS),
                "baseline_parity_turns": len(items),
                "signed_permission_checks": 4,
                "provider_calls": provider.calls,
                "hosted_inference_calls": 0,
                "spend_usd": 0,
                "selected": selected,
                "gates": gates,
                "results": aggregates,
            },
            indent=2,
        )
    )


def main():
    # The existing ONNX wheel can emit runtime telemetry even in Hugging Face offline mode.
    os.environ["ORT_DISABLE_TELEMETRY"] = "1"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    sub = parser.add_subparsers(dest="operation", required=True)
    index = sub.add_parser("index")
    index.add_argument("fixture", type=Path)
    vector = sub.add_parser("serve-vector")
    vector.add_argument("port", type=int)
    vector.add_argument("receipts", type=Path)
    score = sub.add_parser("score")
    score.add_argument("port", type=int)
    score.add_argument("vector_receipts", type=Path)
    score.add_argument("output", type=Path)
    args = parser.parse_args()
    items, support, snapshots, scopes = reviewed(args.root)
    if args.operation == "index":
        seed(snapshots, scopes, args.fixture)
    elif args.operation == "serve-vector":
        if os.environ.get("STUDY_AGENT_ENABLED", "false").lower() != "false":
            raise ValueError("This fixture serves only vector retrieval")
        fd = os.open(args.receipts, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as receipts:
            locked = LockedVector(
                isolated_retriever(), expected_snapshots(snapshots, scopes), receipts
            )
            uvicorn.run(
                vector_app(
                    retriever=locked, secret=os.environ["TUTOR_DEV_SIGNING_KEY"]
                ),
                host="127.0.0.1",
                port=args.port,
                log_level="warning",
            )
    else:
        replay(items, support, snapshots, scopes, args)


if __name__ == "__main__":
    main()
