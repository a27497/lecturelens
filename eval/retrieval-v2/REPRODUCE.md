# Retrieval v2 reproduction

Run from the repository root. Use Python 3.12.14 and the separate evaluation environment; no production dependency, Java endpoint, private API key or reader is needed.

```bash
uv sync --locked --project eval/retrieval-v2 --python 3.12.14
```

## One-command result reproduction

The retained ranks/latencies are the frozen observations. Recompute every metric, bootstrap CI, paired contrast and failure bucket without executing holdout queries again:

```bash
uv run --locked --project eval/retrieval-v2 python -m lecturelens_agent.benchmark_v2.run report \
  --dataset eval/retrieval-v2 \
  --records eval/retrieval-v2/results/development/retrieval.jsonl \
  --records eval/retrieval-v2/results/holdout/retrieval.jsonl \
  --output .data/retrieval-v2/reproduced-report
```

Output must not already exist. The command verifies frozen code/data/dependency hashes and rejects duplicate, missing, foreign or mixed-candidate observations. Outputs summary.json (all K and CI metrics), failures.json (all diagnostic failed queries), provenance.json and RESULTS.md. No weights or source PDFs need to be downloaded for this report command. Fixed bootstrap seed makes regeneration deterministic in the pinned environment; hardware-dependent measured milliseconds remain the saved observations.

## Original retrieval acquisition

This section documents the original run, **not an instruction to score the published holdout a second time**. Prepare an independent PostgreSQL/pgvector database named `*_benchmark`; set `BENCHMARK_DATABASE_URL` through the local environment. Never use a service database. Models are pinned by revisions and file digests in config.json; weights remain in ignored caches. Fixed warmup is unscored, development-only. Do not run pytest, another evaluation or a build concurrently.

```bash
# These commands were run in order, after freezing and after full tests ended.
uv run --locked --project eval/retrieval-v2 python -m lecturelens_agent.benchmark_v2.run collect \
  --dataset eval/retrieval-v2 --split development \
  --output eval/retrieval-v2/results/development --cache .data/agent
uv run --locked --project eval/retrieval-v2 python -m lecturelens_agent.benchmark_v2.run collect \
  --dataset eval/retrieval-v2 --split holdout \
  --output eval/retrieval-v2/results/holdout --cache .data/agent
```

`holdout-attempt.json` is an exclusive one-attempt reservation, created before holdout retrieval, and remains consumed even on failure. Its presence rejects another holdout attempt; do not delete or reset it. Every query/method is retrieved once, with one timed observation. All failures stay in JSONL. Future method tuning needs a new independently authored holdout and a new frozen candidate, not an override flag or revised qrels.

The submitted freeze was created only after split planning, source/annotation preparation, mechanism checks and the fixed config, using the `freeze` subcommand. Existing freezes cannot be overwritten. Source PDFs are licensed MIT OCW materials, recorded by exact URL/hash in source-downloads.json; PDFs/audio/video/weights stay outside Git. SOURCE attribution and CC BY-NC-SA conditions are in SOURCES.md.

Optional source-level audit uses locked pypdf and checks original raw PDF digests and every native normalized page range. `extract_corpus.py` and `build_cases.py` are pre-freeze construction history and refuse to modify the frozen dataset. Do not regenerate the corpus/labels to improve measured scores.

## Mechanism verification

In agent-service's normal environment, point `AGENT_TEST_DATABASE_URL` at a separate PostgreSQL/pgvector test database:

```bash
uv run --project agent-service pytest -q agent-service/tests
uv run --project agent-service ruff check agent-service eval/retrieval-v2/*.py
uv run --project agent-service ruff format --check agent-service/src agent-service/tests eval/retrieval-v2/*.py
```

Mechanics include hand-calculated recall versus fact coverage, family clustering, paired CI, exact two-course sign flips, Wilson intervals, bucket tags, exclusive holdout reservation and frozen course/split integrity. They do not execute the real heldout queries. Full database verification cannot be replaced by skipped tests. Actual test XML/logs and collection coverage are retained separately from retrieval results.
