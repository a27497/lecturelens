"""Run a frozen offline benchmark: python -m lecturelens_agent.benchmark.run --help."""

import argparse
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

from lecturelens_agent.benchmark.core import (
    STRATEGIES,
    Ablations,
    digest,
    percentile,
    retrieval_metrics,
    validate_dataset,
    verify_freeze,
)
from lecturelens_agent.benchmark.reranker import CrossEncoder
from lecturelens_agent.embedding import LocalEmbedding
from lecturelens_agent.store import VectorStore


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    freeze = verify_freeze(args.dataset)
    corpus = json.loads((args.dataset / "corpus.json").read_text())
    cases = json.loads((args.dataset / "cases.json").read_text())
    config = json.loads((args.dataset / "config.json").read_text())
    validate_dataset(corpus, cases)
    dsn = os.environ["BENCHMARK_DATABASE_URL"]
    if not conninfo_to_dict(dsn).get("dbname", "").endswith("_benchmark"):
        raise ValueError("Requires an isolated database named *_benchmark")
    args.output.mkdir(parents=True, exist_ok=False)  # Never overwrite any attempt, including failure.
    identity = {
        "benchmark_id": freeze["id"],
        "freeze_sha256": digest(args.dataset / "freeze.json"),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "packages": {
            name: version(name)
            for name in ("fastembed", "onnxruntime", "psycopg", "torch", "transformers", "numpy")
        },
        "config": config,
        "source_files": freeze["files"],
    }
    write_json(args.output / "identity.json", identity)
    try:
        execute(args, dsn, corpus, cases["cases"], config, identity)
    except Exception as exc:
        # Avoid DSNs/credentials in public error files. Completed JSONL rows remain intact.
        write_json(args.output / "failure.json", {"error_type": type(exc).__name__, "complete": False})
        raise


def execute(args, dsn, corpus, cases, config, identity):
    embedder = LocalEmbedding(str(args.cache))
    from lecturelens_agent.embedding import MODEL_REVISION

    model_dir = (
        args.cache
        / "models/models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/snapshots"
        / MODEL_REVISION
    )
    if {name: digest(model_dir / name) for name in config["dense_files_sha256"]} != config[
        "dense_files_sha256"
    ]:
        raise ValueError("Dense weights/tokenizer differ from frozen model")
    ce_config = config["cross_encoder"]
    ce = CrossEncoder(ce_config)
    store = VectorStore(dsn)
    store.initialize()
    with psycopg.connect(dsn) as conn:
        identity["postgresql"] = conn.execute("SELECT version()").fetchone()[0]
        identity["pgvector"] = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname='vector'"
        ).fetchone()[0]
    identity["index_version"] = embedder.index_version
    identity["cross_encoder_files_sha256"] = ce_config["files_sha256"]
    started = time.perf_counter()
    ablations = Ablations(store, embedder, ce, config)
    for name, course in corpus["courses"].items():
        ablations.prepare(name, course)
    identity["index_preparation_ms"] = (time.perf_counter() - started) * 1000
    write_json(args.output / "identity.json", identity)
    # Warm all paths with a fixed unscored query. Warmup never changes labels/configuration.
    for strategy in STRATEGIES:
        ablations.search("strings", "What does this clip discuss?", strategy)
    rows = []
    with (args.output / "retrieval.jsonl").open("x") as dest:
        for case_index, case in enumerate(cases):
            verify_freeze(args.dataset)
            observed = {strategy: [] for strategy in STRATEGIES}
            rankings = {}
            for repeat in range(config["latency_repeats"]):
                shift = (case_index + repeat) % len(STRATEGIES)
                for strategy in STRATEGIES[shift:] + STRATEGIES[:shift]:
                    started = time.perf_counter()
                    hits = ablations.search(case["course"], case["query"], strategy)
                    observed[strategy].append((time.perf_counter() - started) * 1000)
                    ids = [key for key, _ in hits]
                    if strategy in rankings and ids != [key for key, _ in rankings[strategy]]:
                        raise ValueError("Ranking changed between latency repetitions")
                    rankings[strategy] = hits
            for strategy in STRATEGIES:
                hits = rankings[strategy]
                row = {
                    "case_id": case["id"],
                    "category": case["category"],
                    "strategy": strategy,
                    "answerable": case["answerable"],
                    "hits": [{"evidence_id": k, "score": v} for k, v in hits],
                    "latency_ms": observed[strategy],
                    "metrics": {
                        str(k): retrieval_metrics([key for key, _ in hits], case, k)
                        for k in config["metric_ks"]
                    },
                    "hard_negatives_at_context_k": [
                        key for key, _ in hits[: config["context_k"]] if key in case["hard_negative_ids"]
                    ],
                }
                rows.append(row)
                dest.write(json.dumps(row, ensure_ascii=False) + "\n")
                dest.flush()
                os.fsync(dest.fileno())
            print(case["id"], "retrieved", flush=True)
    summary = {}
    for strategy in STRATEGIES:
        selected = [r for r in rows if r["strategy"] == strategy]
        latency = [v for r in selected for v in r["latency_ms"]]
        summary[strategy] = {
            "queries": len(selected),
            "answerable_queries": sum(r["answerable"] for r in selected),
            "latency_samples": len(latency),
            "p50_ms": percentile(latency, 0.5),
            "p95_ms": percentile(latency, 0.95),
            "metrics": {},
            "by_category": {},
        }
        for k in config["metric_ks"]:
            summary[strategy]["metrics"][str(k)] = average_metrics(selected, k)
        for category in sorted({r["category"] for r in rows}):
            summary[strategy]["by_category"][category] = average_metrics(
                [r for r in selected if r["category"] == category], config["context_k"]
            )
    write_json(args.output / "summary.json", summary)
    bad = [
        r
        for r in rows
        if r["hard_negatives_at_context_k"]
        or r["answerable"]
        and r["metrics"][str(config["context_k"])]["evidence_coverage"] < 1
    ]
    write_json(args.output / "retrieval-bad-cases.json", bad)
    verify_freeze(args.dataset)
    write_json(
        args.output / "complete.json",
        {
            "complete": True,
            "rows": len(rows),
            "retrieval_sha256": digest(args.output / "retrieval.jsonl"),
            "summary_sha256": digest(args.output / "summary.json"),
        },
    )


def average_metrics(rows, k):
    metrics = [r["metrics"][str(k)] for r in rows if r["answerable"]]
    return {name: statistics.mean(m[name] for m in metrics) for name in metrics[0]} if metrics else None


if __name__ == "__main__":
    main()
