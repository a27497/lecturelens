"""Frozen v2 commands: freeze, collect (holdout once), report (offline reproduction)."""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

from ..benchmark.core import STRATEGIES, Ablations, digest, verify_freeze
from .statistics import report, validate_v2


def write(path, value):
    with path.open("x") as file:
        file.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def inputs(directory):
    return [
        json.loads((directory / name).read_text())
        for name in ("corpus.json", "cases.json", "split-plan.json", "config.json")
    ]


def freeze(directory):
    corpus, cases, plan, config = inputs(directory)
    validate_v2(corpus, cases, plan)
    root = directory.resolve().parents[1]
    package = root / "agent-service/src/lecturelens_agent"
    files = [
        directory / name
        for name in (
            "corpus.json",
            "cases.json",
            "split-plan.json",
            "config.json",
            "annotation-seeds.json",
            "source-downloads.json",
            "SOURCES.md",
            "PROTOCOL.md",
            "pyproject.toml",
            "uv.lock",
            "build_cases.py",
            "extract_corpus.py",
        )
    ]
    files += sorted((package / "benchmark_v2").glob("*.py"))
    files += [
        package / name
        for name in (
            "embedding.py",
            "retrieval.py",
            "contracts.py",
            "store.py",
            "benchmark/core.py",
            "benchmark/reranker.py",
        )
    ]
    value = {
        "id": "retrieval-v2-20261014",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "files": {str(p.resolve().relative_to(root)): digest(p) for p in files},
        "packages": {
            p: version(p)
            for p in (
                "fastembed",
                "onnxruntime",
                "psycopg",
                "numpy",
                "torch",
                "transformers",
                "huggingface-hub",
                "pydantic",
                "tokenizers",
            )
        },
        "primary": "Holdout Evidence Coverage@3; three paired contrasts to Dense, Bonferroni familywise alpha=.05",
        "annotation": cases["annotation"],
        "split_plan": plan,
        "config": config,
    }
    write(directory / "freeze.json", value)


def host():
    processes = []
    for line in subprocess.check_output(["ps", "-eo", "pid,args"], text=True).splitlines()[1:]:
        pid, _, command = line.strip().partition(" ")
        # Preserve process category only, never command strings or env/credentials.
        if " -m pytest" in command or "/bin/pytest " in command:
            processes.append({"pid": int(pid), "kind": "pytest"})
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "loadavg": list(os.getloadavg()),
        "pytest_processes": processes,
    }


def collect(args):
    from ..benchmark.reranker import CrossEncoder
    from ..embedding import MODEL_REVISION, LocalEmbedding
    from ..store import VectorStore

    frozen = verify_freeze(args.dataset)
    corpus, dataset, plan, config = inputs(args.dataset)
    validate_v2(corpus, dataset, plan)
    dsn = os.environ["BENCHMARK_DATABASE_URL"]
    if not conninfo_to_dict(dsn).get("dbname", "").endswith("_benchmark"):
        raise ValueError("Use an isolated *_benchmark PostgreSQL database")
    args.output.mkdir(parents=True, exist_ok=False)
    identity = {
        "freeze_sha256": digest(args.dataset / "freeze.json"),
        "split": args.split,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "host_start": host(),
        "packages": frozen["packages"],
        "latency_repeats": 1,
    }
    # Creating this reservation consumes the one holdout attempt even on a crash.
    # Rebuilding summaries from retained ranks does not consume a new attempt.
    if args.split == "holdout":
        write(
            args.dataset / "holdout-attempt.json",
            {
                "freeze_sha256": identity["freeze_sha256"],
                "reserved_at": identity["started_at"],
                "output": str(args.output),
                "policy": "one attempt; no reset or retry",
            },
        )
    write(args.output / "identity.json", identity)
    try:
        embedder = LocalEmbedding(str(args.cache))
        model_dir = (
            args.cache
            / "models/models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/snapshots"
            / MODEL_REVISION
        )
        if {p: digest(model_dir / p) for p in config["dense_files_sha256"]} != config["dense_files_sha256"]:
            raise ValueError("Dense weights differ")
        cross_encoder = CrossEncoder(config["cross_encoder"])
        store = VectorStore(dsn)
        store.initialize()
        with psycopg.connect(dsn) as connection:
            identity["postgresql"] = connection.execute("SELECT version()").fetchone()[0]
            identity["pgvector"] = connection.execute(
                "SELECT extversion FROM pg_extension WHERE extname='vector'"
            ).fetchone()[0]
        engine = Ablations(store, embedder, cross_encoder, config)
        started = time.perf_counter()
        for name, course in corpus["courses"].items():
            engine.prepare(name, course)
        identity["index_preparation_ms"] = (time.perf_counter() - started) * 1000
        # Fixed non-scored development-only query, never a heldout question.
        for strategy in STRATEGIES:
            engine.search(plan["development_courses"][0], "What topics are discussed?", strategy)
        chosen = [c for c in dataset["cases"] if c["split"] == args.split]
        audits = []
        with (args.output / "retrieval.jsonl").open("x") as out:
            for index, case in enumerate(chosen):
                verify_freeze(args.dataset)
                audit = host()
                if audit["pytest_processes"]:
                    raise ValueError("Tests must not overlap timed retrieval")
                audits.append(audit)
                shift = index % len(STRATEGIES)
                for strategy in STRATEGIES[shift:] + STRATEGIES[:shift]:
                    started = time.perf_counter()
                    error = None
                    try:
                        hits = engine.search(case["course"], case["query"], strategy)
                    except (ValueError, RuntimeError, psycopg.Error, OSError) as exc:
                        hits, error = [], type(exc).__name__
                    row = {
                        "case_id": case["id"],
                        "strategy": strategy,
                        "split": args.split,
                        "freeze_sha256": identity["freeze_sha256"],
                        "hits": [{"evidence_id": key, "score": value} for key, value in hits],
                        "latency_ms": (time.perf_counter() - started) * 1000,
                        "error_type": error,
                    }
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
                    os.fsync(out.fileno())
                print(args.split, case["id"], "recorded", flush=True)
        write(args.output / "environment.json", {**identity, "host_finish": host(), "host_audit": audits})
        write(
            args.output / "complete.json",
            {
                "complete": True,
                "queries": len(chosen),
                "rows": len(chosen) * 4,
                "retrieval_sha256": digest(args.output / "retrieval.jsonl"),
            },
        )
    except Exception as exc:
        write(args.output / "failure.json", {"error_type": type(exc).__name__, "complete": False})
        raise


def render(summaries):
    lines = [
        "# Retrieval v2 results",
        "",
        "Frozen AI-assisted qrels; not human gold or Study Agent answer quality.",
        "Family CI conditions on sampled courses; course/family CI also resamples courses. Holdout has only two courses.",
        "",
    ]
    for scope in ("development", "holdout", "all", "zh", "en", "cross-lecture"):
        summary = summaries[scope]
        lines += [
            f"## {scope}",
            "",
            "|Method|Answerable N|Recall@1/3/5/8|MRR@3|nDCG@3|Coverage@3 [family CI95]; [course/family CI95]|P50/P95 ms [CI95]|",
            "|---|---:|---|---:|---:|---|---|",
        ]
        for method, values in summary["methods"].items():
            metrics = values["metrics"]
            cov = metrics["3"]["evidence_coverage"]
            recalls = "/".join(f"{metrics[str(k)]['recall']['estimate'] * 100:.2f}" for k in (1, 3, 5, 8))

            def ci(bounds):
                return f"[{bounds[0] * 100:.2f}, {bounds[1] * 100:.2f}]"

            def latency(key, values=values):
                m = values["latency"][key]
                return f"{m['estimate_ms']:.2f} [{m['ci95_ms'][0]:.2f}, {m['ci95_ms'][1]:.2f}]"

            lines.append(
                f"|{method}|{values['answerable_queries']}|{recalls}|{metrics['3']['mrr']['estimate']:.4f}|{metrics['3']['ndcg']['estimate']:.4f}|{cov['estimate'] * 100:.2f} {ci(cov['ci'])}; {ci(cov['ci95_course_family'])}|{latency('p50')} / {latency('p95')}|"
            )
        lines += [
            "",
            "Prespecified paired Coverage@3 contrasts to Dense (percentage points; simultaneous Bonferroni intervals):",
            "",
        ]
        for name, value in summary["paired_primary_comparisons"].items():
            lines.append(
                f"- {name}: {value['estimate'] * 100:.2f}; family {ci(value['ci'])}; course/family {ci(value['ci_course_family_bonferroni'])}"
            )
        lines += [
            "",
            "Failure bucket counts/shares and all per-metric CIs at K=1/3/5/8 are in summary.json; every failed query is retained in failures.json.",
            "",
        ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("freeze", "collect", "report"):
        p = sub.add_parser(name)
        p.add_argument("--dataset", type=Path, required=True)
        if name != "freeze":
            p.add_argument("--output", type=Path, required=True)
        if name == "collect":
            p.add_argument("--split", choices=("development", "holdout"), required=True)
            p.add_argument("--cache", type=Path, required=True)
        if name == "report":
            p.add_argument("--records", type=Path, action="append", required=True)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.dataset)
    elif args.action == "collect":
        collect(args)
    else:
        verify_freeze(args.dataset)
        corpus, cases, plan, config = inputs(args.dataset)
        validate_v2(corpus, cases, plan)
        rows = [
            json.loads(line)
            for path in args.records
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        expected = digest(args.dataset / "freeze.json")
        if any(r.get("freeze_sha256") != expected for r in rows):
            raise ValueError("Ranks belong to a different frozen candidate")
        summaries, failures = report(rows, cases, corpus, config)
        args.output.mkdir(parents=True, exist_ok=False)
        write(args.output / "summary.json", summaries)
        write(args.output / "failures.json", failures)
        write(
            args.output / "provenance.json",
            {
                "freeze_sha256": expected,
                "records": {str(p): digest(p) for p in args.records},
                "bootstrap": config["bootstrap_draws"],
                "seed": config["bootstrap_seed"],
            },
        )
        with (args.output / "RESULTS.md").open("x") as file:
            file.write(render(summaries))
        print("report complete", len(rows), "observations", len(failures), "diagnostic failures")


if __name__ == "__main__":
    main()
