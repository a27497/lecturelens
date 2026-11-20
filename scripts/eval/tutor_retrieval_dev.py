"""Replay frozen L4 dev questions through the Tutor retrieval context, without model calls."""

import argparse
import hashlib
import json
import math
import os
import statistics
from pathlib import Path
from types import SimpleNamespace

import psycopg
import uvicorn
from lecturelens_agent.app import create_app
from lecturelens_agent.contracts import Evidence, EvidenceMetadata, SyncRequest
from lecturelens_agent.embedding import LocalEmbedding
from lecturelens_agent.retrieval import Retriever, split_evidence
from lecturelens_agent.store import VectorStore
from lecturelens_agent.study.authority import EvidenceAuthority
from lecturelens_real_eval.l4.blind import sha256
from lecturelens_real_eval.l4.questions import ORDER, load_frozen
from lecturelens_real_eval.tutor.light import LightTutorRuntime
from lecturelens_real_eval.tutor.light_retrieval import MAX_CONTEXT, retrieve_context

BASELINES = {
    "main": "MAIN",
    "dense-8": "DENSE_8",
}
ABLATIONS = {
    "hybrid-8": "HYBRID_8",
    "hybrid-16": "HYBRID_16",
    "hybrid-8-neighbors": "HYBRID_8_NEIGHBORS",
}
ROUTED = {
    "routed-hybrid-8": ("HYBRID_8", "HYBRID_8"),
    "routed-hybrid-16": ("HYBRID_8", "HYBRID_16"),
    "routed-hybrid-8-neighbors": ("HYBRID_8", "HYBRID_8_NEIGHBORS"),
}


def write_private(path, data):
    with open(
        path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)
    ) as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def inputs(root):
    items = load_frozen(root, "dev")
    if len(items) != 30 or sum(i["answerable"] for i in items) != 24:
        raise ValueError("Unexpected L4 dev population")
    lectures = sorted({i["lecture_id"] for i in items})
    snapshots = {
        lecture: json.loads((root / "evidence" / f"{lecture}.json").read_bytes())
        for lecture in lectures
    }
    scopes = {
        lecture: dict(
            owner_id=d["owner_id"], course_id=d["task_id"], revision=d["revision"]
        )
        for lecture, d in snapshots.items()
    }
    return items, snapshots, scopes


def isolated_retriever():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        if conn.info.dbname != "lecturelens_agent_test":
            raise ValueError("Use a dedicated lecturelens_agent_test database")
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        raise ValueError("Set HF_HUB_OFFLINE=1 and supply an existing embedding cache")
    return Retriever(
        VectorStore(dsn), LocalEmbedding(os.environ["TUTOR_DEV_EMBEDDING_CACHE"])
    )


def index(root, fixture_path):
    _, snapshots, scopes = inputs(root)
    retriever = isolated_retriever()
    retriever.store.initialize()
    manifest = []
    for lecture, snapshot in snapshots.items():
        scoped = scopes[lecture]
        rows = []
        for e in snapshot["items"]:
            if (e["ownerId"], e["courseId"], e["revision"]) != tuple(scoped.values()):
                raise ValueError("Mixed frozen evidence scope")
            if e["retrievable"]:
                rows.append(
                    Evidence(
                        evidence_id=e["evidenceId"],
                        text=e["normalizedText"],
                        start_ms=e["startMs"],
                        end_ms=e["endMs"],
                    )
                )
        if (
            retriever.sync(
                SyncRequest(
                    request_id="tutor-dev-index",
                    **scoped,
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
            )["state"]
            != "READY"
        ):
            raise ValueError("Dev index was not published")
        manifest.extend(
            (row.evidence_id, hashlib.sha256(text.encode()).hexdigest())
            for row, text in split_evidence(rows)
        )
    write_private(fixture_path, list(snapshots.values()))
    print(
        json.dumps(
            {
                "snapshot_sha256": sha256(list(snapshots.values())),
                "chunks_sha256": sha256(manifest),
                "chunks": len(manifest),
                "index_version": retriever.embedder.index_version,
            }
        )
    )


def measure(item, evidence, support, query_count):
    ids = {row["evidence_id"] for row in evidence}
    if len(ids) != len(evidence):
        raise ValueError("Duplicate final context")
    coverage = {
        nugget: any(set(group) <= ids for group in alternatives)
        for nugget, alternatives in support.get(item["item_id"], {}).items()
    }
    return {
        "category": item["category"],
        "answerable": item["answerable"],
        "nuggets": coverage,
        # UTF-8 byte count of the exact current_evidence array as serialized by Light Tutor.
        "context_bytes": len(json.dumps(evidence, ensure_ascii=False).encode()),
        "chunks": len(ids),
        "queries": query_count,
        "selected": [row["evidence_id"] for row in evidence],
    }


def summary(rows):
    def stats(values):
        return {
            "mean": round(statistics.mean(values), 2),
            "p95": sorted(values)[math.ceil(len(values) * 0.95) - 1],
            "max": max(values),
        }

    answerable = [r for r in rows if r["answerable"]]
    return {
        "items": len(rows),
        "full": [sum(all(r["nuggets"].values()) for r in answerable), len(answerable)],
        "vital": [
            sum(sum(r["nuggets"].values()) for r in answerable),
            sum(len(r["nuggets"]) for r in answerable),
        ],
        "chunks": stats([r["chunks"] for r in rows]),
        "context_bytes": stats([r["context_bytes"] for r in rows]),
        "multi_query": sum(r["queries"] > 1 for r in rows),
    }


def gate(baseline, candidate):
    guarded = ORDER[3:5]
    return (
        candidate["answerable"]["full"][0] >= baseline["answerable"]["full"][0] + 2
        and all(candidate[k]["full"][0] >= baseline[k]["full"][0] for k in guarded)
        and candidate["overall"]["chunks"]["max"] <= MAX_CONTEXT
    )


def evaluate(root, support_path, authority, phase):
    items, snapshots, scopes = inputs(root)
    support = json.loads(support_path.read_bytes())
    required = {
        i["item_id"]: {n["id"] for n in i["nuggets"] if n["importance"] == "vital"}
        for i in items
        if i["answerable"]
    }
    if {item_id: set(nuggets) for item_id, nuggets in support.items()} != required:
        raise ValueError(
            "Support groups must cover exactly the frozen answerable vital nuggets"
        )
    for item in items:
        known = {
            e["evidenceId"]
            for e in snapshots[item["lecture_id"]]["items"]
            if e["retrievable"]
        }
        for alternatives in support.get(item["item_id"], {}).values():
            if not alternatives or any(
                not group or len(group) != len(set(group)) or set(group) - known
                for group in alternatives
            ):
                raise ValueError(
                    "Support group outside the frozen retrievable snapshot"
                )
    options = BASELINES if phase == "baseline" else ABLATIONS
    configurations = {
        name: (strategy, strategy, False) for name, strategy in options.items()
    }
    if phase == "candidate":
        configurations |= {
            name: (*strategies, True) for name, strategies in ROUTED.items()
        }
        configurations["product"] = (None, None, True)
    runtime = LightTutorRuntime(SimpleNamespace(engine="light"), authority)
    output, private = {}, {}
    for name, (simple, complex_, route) in configurations.items():
        per_item = {}
        for item in items:
            scope = scopes[item["lecture_id"]]
            if name == "product":
                state = runtime.prepare(
                    scope, {"learner_text": item["question"], "socratic": False}, []
                )
                evidence = json.loads(state["messages"][-1]["content"])[
                    "current_evidence"
                ]
                searches = state["searches"]
            else:
                ids, searches = retrieve_context(
                    authority,
                    scope,
                    item["question"],
                    [],
                    simple=simple,
                    complex_=complex_,
                    route=route,
                )
                evidence = runtime.read_evidence(scope, ids)
            per_item[item["item_id"]] = measure(item, evidence, support, len(searches))
        rows = list(per_item.values())
        output[name] = {
            "overall": summary(rows),
            "answerable": summary([r for r in rows if r["answerable"]]),
            "should_abstain": summary([r for r in rows if not r["answerable"]]),
        } | {
            category: summary([r for r in rows if r["category"] == category])
            for category in ORDER
            if any(r["category"] == category for r in rows)
        }
        private[name] = per_item
    return {
        "dev_sha256": hashlib.sha256(
            (root / "questions/questions.dev.json").read_bytes()
        ).hexdigest(),
        "support_sha256": hashlib.sha256(support_path.read_bytes()).hexdigest(),
        "snapshot_sha256": sha256(list(snapshots.values())),
        "results": output,
    }, private


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("index")
    seed.add_argument("root", type=Path)
    seed.add_argument("fixture", type=Path)
    vector = sub.add_parser("serve-vector")
    vector.add_argument("port", type=int)
    score = sub.add_parser("score")
    score.add_argument("phase", choices=("baseline", "candidate"))
    score.add_argument("root", type=Path)
    score.add_argument("support", type=Path)
    score.add_argument("port", type=int)
    score.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "index":
        index(args.root, args.fixture)
    elif args.command == "serve-vector":
        if os.environ.get("STUDY_AGENT_ENABLED", "false").lower() != "false":
            raise ValueError("This fixture serves only vector retrieval")
        uvicorn.run(
            create_app(
                retriever=isolated_retriever(),
                secret=os.environ["TUTOR_DEV_SIGNING_KEY"],
            ),
            host="127.0.0.1",
            port=args.port,
            log_level="warning",
        )
    else:
        authority = EvidenceAuthority(
            f"http://127.0.0.1:{args.port}", os.environ["TUTOR_DEV_SIGNING_KEY"]
        )
        aggregates, private = evaluate(args.root, args.support, authority, args.phase)
        write_private(args.output, private)
        print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
