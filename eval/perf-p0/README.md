# Performance P0 harness preparation

This directory measures **Mock execution mechanics**, with the existing retrieval
busy lock left intact. Development runs are labeled **DEV_SMOKE_NOT_RESUME** in
both JSON and Markdown. They are neither rental-machine baselines nor resume
numbers. Rental-machine full runs, real-model Tutor quality, expanded/held-out
Tutor evaluation and blind review are **NOT_RUN** in this stage.

Only this directory is added. No product source, worker count, lock, budget,
frozen identity, workflow or online configuration is changed. The eval-only
adapters below must be included in comparisons; they are not a product release.

## Prerequisites and one-command entrypoints

Use a clean committed checkout on Linux with Docker access, Docker Compose
>=2.24.4 (`!override`), Java **21** plus `javac`, Python >=3.12, `uv`, FFmpeg and
Bash. The Maven wrapper and `uv.lock` resolve existing pinned dependencies. No
provider account, API key, model download or existing `.env` is needed. First use
can download public application dependencies/container images; `--offline`
requires all of them cached. If the pinned MinIO release registry is unavailable,
add `--build-minio` to use the repository's existing CI source-pinned build recipe
(allow extra bootstrap time). This build alternative has not been exercised by
the development smoke and must be compared using its recorded image IDs.

From the repository root, run a small healthy-path smoke:

```bash
python3 scripts/dev/run_check.py --name perf-dev-health \
  --output .data/perf-p0/checks --timeout 1200 -- \
  bash eval/perf-p0/run.sh --profile dev --concurrency 1 --requests 3 \
  --mock-delay-ms 25 --output .data/perf-p0/dev-health
```

Then directly exercise lock contention in a separate fresh environment:

```bash
python3 scripts/dev/run_check.py --name perf-dev-busy \
  --output .data/perf-p0/checks --timeout 1200 -- \
  bash eval/perf-p0/run.sh --profile dev --scenarios S1 --concurrency 1,8 \
  --requests 64 --output .data/perf-p0/dev-busy
```

Each invocation creates and removes its own stack, rather than connecting to an
existing preview. Use a new output directory each time. Add `--offline` for cached
development runs. Dev mode caps concurrency at 32, requests at 200 per group, or
admission time at 10 seconds per group. `--allow-dirty` is diagnostic only and
cannot produce clean-source evidence accepted by `verify.py`.

**Rental entrypoint, only after the user separately approves the rental period:**

```bash
python3 scripts/dev/run_check.py --name perf-rental-mock \
  --output .data/perf-p0/checks --timeout 7200 -- \
  bash eval/perf-p0/run.sh --profile rental --scenarios S1,S2,S3 \
  --concurrency 1,4,8,16 --seconds 60 --timeout 60 --mock-delay-ms 150 \
  --qa-per-minute 100000 --output .data/perf-p0/rental-mock-01
```

The rental profile refuses fewer than 16 available logical CPUs or 60 GB memory,
including detected cgroup limits. This is a guard against running the full matrix
on a small development machine, not proof of dedicated hardware. Record the
provider's machine specification separately. The example explicitly raises the
**existing isolated QA per-owner rate limit** from its preserved default of 10
per minute; it does not disable authentication or change product code. Keep 10
when measuring the policy envelope. A 429 is an error in the denominator, not
successful capacity. Warmups and preceding groups consume the same limit window.

No rental command has been run in this stage. Repeat independent runs on the
rented machine before interpreting variance; compare only matching workload,
delay, image/config fingerprints and hardware. These defaults are a synthetic
single-course baseline, not production sizing or a semantic embedding benchmark.

## Three distinct denominators

| Scenario | One logical attempt and success boundary | Included work |
|---|---|---|
| S1 pure retrieve | One signed `POST /internal/v1/retrieve`; HTTP 200 with nonempty, owner/course/revision-fenced hits | Python HTTP, original nonblocking `Retriever.search()` lock, deterministic hash embedding, real PostgreSQL vector query; bypasses Java/Study orchestration |
| S2 Java QA | Authenticated `POST /api/tasks/{id}/qa`; code 0, answer and Evidence present | Java auth/MySQL authority, QA rate limit, Java→Python retrieval, existing DemoMock QA generation, saved QA result |
| S3 P8 Tutor | Create fresh Session, submit one turn, poll until **completed** with an answered result and citations | Java auth/authority, Python original Tutor loop/worker, course Evidence tools, PostgreSQL checkpoints, two normal Mock decisions, queue and polling delay |

S3 submission HTTP 200 means accepted, **not completed**. A fresh Session per
attempt avoids accumulated Session budget exhaustion without changing budgets.
The default original single Tutor worker is preserved. S3 is not a multi-turn
teaching-quality evaluation. Each scenario runs sequentially; concurrency groups
run in the requested order. No mixed S1/S2/S3 workload is claimed.

The historical Phase E **90 attempted / 31 failed** count described whole Study
Runs failing at SEARCH. It is not a direct-retrieve sample and must not be merged
with S1's per-request denominator. Java QA and Tutor also have their own distinct
logical-operation and HTTP-request counts.

## Isolation, corpus and timing adapters

The runner reuses `scripts/ci/mock-study-tutor-e2e.py` for fresh infrastructure,
readiness, synthetic account registration, chunked video upload, media pipeline
and index preparation. It composes the root infrastructure definition with a
generated **127.0.0.1-only** port override and uses this directory's independent
PostgreSQL Compose definition. Each run has random
`lecturelens-perf-p0-<nonce>-infra` / `-pg` projects and private volumes. All ports
are checked, selected free and recorded; actual container bindings are checked
again. Java and Uvicorn bind loopback. No existing business database, account,
service, production configuration or other worktree is used.

The corpus is the repository-generated two-second synthetic video and existing
DemoMock ASR/translation output. One owner, one course/revision and its allowed
Evidence set are shared by all load workers. Video/text hashes, Evidence and
vector chunk counts are recorded. This deliberately small hot-course workload
cannot establish large-index, diverse-course or cold-cache capacity.

`perf_app.py` injects deterministic **hash384** embeddings into the original
Retriever/VectorStore. No embedding sleep, forced lock acquisition or synthetic
503 is injected. Therefore a busy 503 is the real application admission failure,
but its frequency includes this embedding/corpus choice and cannot be compared
as production encoder throughput. No embedding model weights are fetched.

`--mock-delay-ms` (default 25, range 0–5000) sleeps **inside** the eval wrappers:

- S2: `java/PerfMain.java` loads the jar's original Spring application source and
  explicitly installs `PerfDelayInitializer`. The initializer wraps only the
  existing `DemoMockLlmProvider`; any other LlmProvider is rejected. Delay applies
  only to `COURSE_QA`, not course preparation. Original packaged application
  classes and QA logic are retained; addon classes live outside the jar. The
  delegate's synthetic usage/duration metadata is unchanged; use harness wall
  latency for timing, not that metadata.
- S3: `DelayedMockTutor` sleeps once per `decide`, then delegates to the existing
  MockTutor. A normal supported turn makes two decisions. No worker/budget/tool
  or frozen Tutor source is edited. Logs attest each wrapper was actually used.

Only generated secrets are passed in child environments; logs redact them.
Provider credentials, proxies, JVM options and application configuration are not
inherited. Real Java providers are disabled, the wrapper rejects real providers,
`AGENT_LLM_MODE=mock`, and an Agent interpreter audit hook rejects non-loopback
socket connections. This does not claim OS-level Java egress attribution. Public
dependency downloads during bootstrap are separate from model calls. LLM spend
is $0; Mock token counters are not real-provider cost measurements.

## Measurement and output contract

Closed-loop workers admit the next operation after the previous one finishes.
There is no target QPS/open-loop schedule and no HTTP retry, backoff or redirect.
`Retry-After` is recorded but not obeyed by retrying. All attempts are retained,
including timeouts, HTTP errors, business errors inside HTTP 200, malformed
results and failed/cancelled Tutor turns. The runner exiting zero means the
harness completed and cleaned up, **not** that a load group had zero errors.
Every selected path must first pass one excluded, low-concurrency warmup.

Choose `--requests N` (total across workers per group) or `--seconds S` (admission
window). After admission stops, in-flight work drains within each operation's
timeout. Wall time includes drain and HTTP-client setup; operation latency runs
from admission through validation/completion. A failed S3 attempt cancels and
drains its own turn with an additional bounded eight-second cleanup window;
latency includes that cleanup and an undrained turn stops subsequent groups.
Do not interpret a timeout as an absent or successful observation.

- `result.json`: schema/config, label, Git SHA + dirty/source drift checks, CPU
  model/count/affinity/cgroup limits, RAM/kernel/architecture, Python/Java/Docker/
  Compose versions, jar/file/image hashes, corpus/config fingerprints, stages,
  warmups, per-group counts, error rate and throughput.
- `requests.jsonl`: one row per logical attempt, with warmup flag, latency, HTTP
  request/poll counts, last operation HTTP status, error category and Retry-After.
  No tokens, headers, prompts, answers or passwords are written here. Cancel
  cleanup requests are counted separately and do not overwrite the error status.
- `REPORT.md`: concise group table and NOT_RUN list. P50/P95 use nearest rank in
  milliseconds; JSON separates **all / successful / failed** latency samples.
  Empty percentiles/error rates are null. `error_rate = failed / attempted`;
  attempted and successful throughput each divide by actual drained wall time.
  Fast failures can lower all-attempt percentiles, so inspect successful P95 too.
- Redacted service/bootstrap logs, `public.env` (no generated secrets), generated
  Compose overrides, compiled addon/extracted jar files and cleanup evidence stay
  in the private output directory. `file_sha256` and `config_sha256` describe
  inputs; the result has no claim to cryptographic third-party attestation.

Verify final clean-source evidence and recompute metrics from raw rows:

```bash
agent-service/.venv/bin/python eval/perf-p0/verify.py .data/perf-p0/dev-health \
  --sha "$(git rev-parse HEAD)"
agent-service/.venv/bin/python eval/perf-p0/verify.py .data/perf-p0/dev-busy \
  --sha "$(git rev-parse HEAD)" --require-busy
```

Expected 503s never turn into a synthetic pass: `--require-busy` fails unless S1
actually observed `503 / Retrieval busy` and `Retry-After: 1`. If this machine
cannot reproduce it within the bounded smoke, retain that observation honestly.

Normal completion, errors, Ctrl-C and SIGTERM run owned cleanup, verify no
containers/volumes/networks remain and retain failure logs. Use the supervisor's
Ctrl-C/timeout path; never suspend a sudo child or kill processes by broad name.
After SIGKILL/host failure, remove only the recorded Compose projects with:

```bash
python3 eval/perf-p0/cleanup.py .data/perf-p0/dev-health
```

Emergency cleanup needs no original password; it removes recorded resources,
not application processes. Stop surviving Java/Agent children via the original
supervisor/session, verifying their recorded command/output directory first.

## Targeted verification

```bash
agent-service/.venv/bin/ruff check eval/perf-p0
agent-service/.venv/bin/ruff format --check eval/perf-p0
bash -n eval/perf-p0/run.sh
python3 scripts/dev/run_check.py --name perf-harness-unit \
  --output .data/perf-p0/checks --timeout 120 -- \
  agent-service/.venv/bin/python -m unittest discover -s eval/perf-p0 -p test_harness.py -v
```

Self-tests use simulated HTTP only to verify harness accounting/protocol rules;
they do not replace the fresh Java→Python→MySQL/PostgreSQL smoke above. Java addon
compilation and actual wrapper use are checked by each service smoke. No product
or shared Study code changed, so Agent full pytest, frontend build and product
Java suites are NOT_RUN for this harness-only change. Existing development and
Tutor frozen hashes can be checked without rewriting any manifest.
