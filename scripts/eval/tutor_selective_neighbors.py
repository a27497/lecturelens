"""Score the three LL-P15 retrieval arms once on the frozen L4 dev packet."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from lecturelens_agent.app import create_app
from lecturelens_agent.study.authority import EvidenceAuthority
from lecturelens_real_eval.l4.questions import ORDER
from lecturelens_real_eval.tutor.light import LightTutorRuntime
from lecturelens_real_eval.tutor.light_retrieval import MAX_CONTEXT, retrieve_context
from tutor_retrieval_dev import (
    inputs,
    isolated_retriever,
    measure,
    sha256,
    summary,
    write_private,
)

RULES_SHA256 = "8ee0a46af701f431cb0d7f4691902bb0c1eb76cb938f8ed4c068ea73d10a9831"
INPUTS = {
    "dev_sha256": "5b8969ec75a410fb2fcc843636cf2443540ec91d7449004908310a7185489bdd",
    "support_sha256": "510fbb48c7018c6129c2ceb89f51130ef42b47b0c78b4d66963e0effba9528af",
    "snapshot_sha256": "a900b6915ead8d2935ca260879718dff20296731c5651f756d1f520759d8e4b6",
    "chunks_sha256": "bb7fa578acdfcd89f0668bae4221426cb775c5d65eda0b87b0201227fe12cb4e",
    "chunks": 1006,
    "index_version": "minilm-multi:faf4aa4225822f3bc6376869cb1164e8e3feedd0:fastembed-0.8.0:chars240-overlap40-v1",
}
ARMS = {
    "main": {"simple": "HYBRID_8", "complex_": "HYBRID_16"},
    "all_queries_neighbors": {
        "simple": "HYBRID_8_NEIGHBORS",
        "complex_": "HYBRID_8_NEIGHBORS",
    },
    "selective": {},
}


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locked_inputs(root, support_path, index_receipt):
    rules = (
        Path(__file__).resolve().parents[2]
        / "eval/tutor-selective-neighbors/PREREGISTRATION.md"
    )
    if file_sha(rules) != RULES_SHA256:
        raise ValueError("Preregistered retrieval rules changed")
    items, snapshots, scopes = inputs(root)
    observed = {
        **json.loads(index_receipt.read_bytes()),
        "dev_sha256": file_sha(root / "questions/questions.dev.json"),
        "support_sha256": file_sha(support_path),
    }
    if (
        observed != INPUTS
        or sha256(list(snapshots.values())) != INPUTS["snapshot_sha256"]
    ):
        raise ValueError("Frozen dev inputs or index changed")
    return (
        items,
        scopes,
        json.loads(support_path.read_bytes()),
        expected_snapshots(snapshots, scopes),
    )


def expected_snapshots(snapshots, scopes):
    expected = {}
    for lecture, snapshot in snapshots.items():
        scope = scopes[lecture]
        key = (scope["owner_id"], scope["course_id"], scope["revision"])
        ids = sorted(
            row["evidenceId"] for row in snapshot["items"] if row["retrievable"]
        )
        # VectorStore publishes this identity from the full Evidence ID manifest.
        payload = json.dumps([*key, INPUTS["index_version"], ids]).encode()
        expected[key] = hashlib.sha256(payload).hexdigest()
    return expected


class LockedVector:
    def __init__(self, retriever, expected, receipts):
        self.retriever = retriever
        self.embedder = retriever.embedder
        self.expected = expected
        self.receipts = receipts
        if self.embedder.index_version != INPUTS["index_version"]:
            raise ValueError("Vector service has a different embedding version")

    def search(self, request):
        result = self.retriever.search(request)
        key = (result.owner_id, result.course_id, result.revision)
        if result.index_version != INPUTS[
            "index_version"
        ] or result.snapshot_id != self.expected.get(key):
            raise ValueError("Vector response does not match the frozen index")
        self.receipts.write(
            json.dumps([*key, result.index_version, result.snapshot_id]) + "\n"
        )
        self.receipts.flush()
        return result


def check_vector_receipts(receipts, scope, expected, queries):
    key = (scope["owner_id"], scope["course_id"], scope["revision"])
    identity = [*key, INPUTS["index_version"], expected[key]]
    pages = [json.loads(line) for line in receipts]
    # Each query makes one dense request, with a second page when available.
    if not queries <= len(pages) <= 2 * queries or any(
        page != identity for page in pages
    ):
        raise ValueError("Missing or mismatched live vector receipts")
    return identity[-1]


def evaluate(items, scopes, support, authority, receipts, vector_receipts, expected):
    runtime = LightTutorRuntime(SimpleNamespace(engine="light"), authority)
    rows = {name: [] for name in ARMS}
    for item in items:
        scope = scopes[item["lecture_id"]]
        plans = []
        for arm, strategies in ARMS.items():
            if strategies:
                ids, searches = retrieve_context(
                    authority, scope, item["question"], [], **strategies
                )
                evidence = runtime.read_evidence(scope, ids)
            else:
                state = runtime.prepare(
                    scope, {"learner_text": item["question"], "socratic": False}, []
                )
                evidence = json.loads(state["messages"][-1]["content"])[
                    "current_evidence"
                ]
                searches = state["searches"]
            snapshot_id = check_vector_receipts(
                vector_receipts, scope, expected, len(searches)
            )
            row = measure(item, evidence, support, len(searches))
            queries = [search["query"] for search in searches]
            record = {
                "arm": arm,
                "item_id": item["item_id"],
                "query_plan_sha256": sha256(queries),
                "vector_snapshot_id": snapshot_id,
                **row,
            }
            receipts.write(json.dumps(record, ensure_ascii=False) + "\n")
            receipts.flush()
            if row["chunks"] > MAX_CONTEXT:
                raise ValueError("Context exceeds the fixed cap")
            plans.append(tuple(query.encode("utf-8") for query in queries))
            if plans[-1] != plans[0]:
                raise ValueError("Query plan differs from main")
            rows[arm].append(row)
    return rows


def summarize(rows):
    groups = {
        "all_items": rows,
        "answerable": [row for row in rows if row["answerable"]],
        "refusals": [row for row in rows if not row["answerable"]],
    } | {
        category: [row for row in rows if row["category"] == category]
        for category in ORDER
        if any(row["category"] == category for row in rows)
    }
    results = {key: summary(group) for key, group in groups.items()}
    for key, group in groups.items():
        if not all(row["answerable"] for row in group):
            del results[key]["full"], results[key]["vital"]
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve-vector")
    score = commands.add_parser("score")
    for command in (serve, score):
        command.add_argument("root", type=Path)
        command.add_argument("support", type=Path)
        command.add_argument("index_receipt", type=Path)
        command.add_argument("port", type=int)
        command.add_argument("vector_receipts", type=Path)
    score.add_argument("output", type=Path, help="new private output directory")
    args = parser.parse_args()
    items, scopes, support, expected = locked_inputs(
        args.root, args.support, args.index_receipt
    )
    signing_key = os.environ["TUTOR_DEV_SIGNING_KEY"]
    if args.command == "serve-vector":
        if os.environ.get("STUDY_AGENT_ENABLED", "false").lower() != "false":
            raise ValueError("This fixture serves only vector retrieval")
        with open(args.vector_receipts, "x", opener=private_file) as out:
            vector = LockedVector(isolated_retriever(), expected, out)
            uvicorn.run(
                create_app(retriever=vector, secret=signing_key),
                host="127.0.0.1",
                port=args.port,
            )
        return
    authority = EvidenceAuthority(f"http://127.0.0.1:{args.port}", signing_key)
    args.output.mkdir(mode=0o700)
    path = args.output / "cases.jsonl"
    with (
        args.vector_receipts.open() as vector_in,
        open(path, "x", opener=private_file) as out,
    ):
        if vector_in.read(1):
            raise ValueError("Use a new vector receipt file for the replay")
        rows = evaluate(items, scopes, support, authority, out, vector_in, expected)
    write_private(
        args.output / "aggregates.json",
        {
            "rules_sha256": RULES_SHA256,
            "inputs": INPUTS,
            "cases_sha256": file_sha(path),
            "vector_snapshot_ids": sorted(expected.values()),
            "results": {name: summarize(arm_rows) for name, arm_rows in rows.items()},
        },
    )


def private_file(name, flags):
    return os.open(name, flags, 0o600)


if __name__ == "__main__":
    main()
