# Performance P0 harness

P11-A review: [findings and deterministic evidence](P11_A_REVIEW.md) (historical:
it describes the pre-Step-6 single retrieval lock and schema v2).
The approved-independent-machine procedure is [P11_RENTAL_PLAN.md](P11_RENTAL_PLAN.md).
Do not start services or execute load on the shared SameScale server. Commands
that create a stack below are for a separately approved disposable host only.

The runner measures **Mock execution mechanics** of the Step 6 concurrency lanes
([AGENT_CONCURRENCY.md](../../docs/AGENT_CONCURRENCY.md)) with their product
admission code unchanged. Each invocation sets `AGENT_RETRIEVAL_CONCURRENCY`
(`--retrieval-concurrency`, product default 4, range 1–16) and
`AGENT_RUN_CONCURRENCY` (`--run-concurrency`, default 2, range 1–8); defaults and
ranges are imported from the product modules. Development runs are labeled **DEV_SMOKE_NOT_RESUME** in
both JSON and Markdown. They are neither rental-machine baselines nor resume
numbers. Rental-machine full runs, real-model Tutor quality, expanded/held-out
Tutor evaluation and blind review are **NOT_RUN** in this stage.

Only this directory is changed. No product source, default lane count, lock,
budget, frozen identity, workflow or online configuration is changed. The
eval-only adapters below must be included in comparisons; they are not a product
release.

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
  --output .data/perf-p0/checks --timeout 1800 -- \
  bash eval/perf-p0/run.sh --profile dev --concurrency 1 --requests 3 \
  --mock-delay-ms 25 --output .data/perf-p0/dev-health
```

Then directly exercise query-slot contention in a separate fresh environment:

```bash
python3 scripts/dev/run_check.py --name perf-dev-busy \
  --output .data/perf-p0/checks --timeout 1800 -- \
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
  --output .data/perf-p0/checks --timeout 7800 -- \
  bash eval/perf-p0/run.sh --profile rental --scenarios S1,S2,S3,S4 \
  --concurrency 1,4,8,16 --seconds 60 --timeout 60 --mock-delay-ms 150 \
  --retrieval-concurrency 4 --run-concurrency 2 \
  --qa-per-minute 100000 --run-deadline 7200 --output .data/perf-p0/rental-mock-01
```

The L2 matrix in [P11_RENTAL_PLAN.md](P11_RENTAL_PLAN.md) splits this into
smaller invocations per lane configuration; use that plan for formal points.

The rental profile refuses fewer than 16 available logical CPUs or 60 GB memory,
including visible cgroup v2 ancestor limits; unknown limits fail closed. This is a guard against running the full matrix
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
| S1 pure retrieve | One signed `POST /internal/v1/retrieve`; HTTP 200 with nonempty, owner/course/revision-fenced hits | Python HTTP, product `Retriever.search()` query slots (`AGENT_RETRIEVAL_CONCURRENCY`), deterministic hash embedding, real PostgreSQL vector query; bypasses Java/Study orchestration |
| S2 Java QA | Authenticated `POST /api/tasks/{id}/qa`; code 0, answer and Evidence present | Java auth/MySQL authority, QA rate limit, Java→Python retrieval (same query slots), existing DemoMock QA generation, saved QA result |
| S3 P8 Tutor | Create fresh Session, submit one turn, poll until **completed** with an answered result and citations | Java auth/authority, Python experimental Tutor (`real_eval`) loop with its **single** `tutor-worker` thread, course Evidence tools, PostgreSQL checkpoints, two normal Mock decisions, queue and polling delay |
| S4 Study Run | Create fresh Study Session, `GENERATE_CARDS`, poll `READ` until **succeeded**, then `EVENTS` must contain `deck_created` with ≥1 card | Java Study gateway/authority, Python `StudyRuntime` dispatcher + `AGENT_RUN_CONCURRENCY` worker lanes, two delayed Mock flashcard decisions, one Java-authorized SEARCH (query slots), budgets, checkpoints, queue and polling delay |

S3/S4 submission HTTP 200 means accepted, **not completed**. A fresh Session per
attempt avoids accumulated Session budget exhaustion without changing budgets,
and lets S4 Runs use separate lanes (same-Session Runs are serialized by design).
`AGENT_RUN_CONCURRENCY` governs only S4: the Tutor runtime is a separate
single-worker loop, so S3 queueing shows that worker, not the Run lanes. Flashcards
is the only Run kind with an end-to-end Mock path in the existing CI smoke; S4
does not measure practice/feedback Runs or real-model latency. Neither S3 nor S4
is a multi-turn teaching-quality evaluation. Each scenario runs sequentially;
concurrency groups run in the requested order. No mixed workload is claimed.

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

`perf_app.py` injects deterministic **hash384** embeddings into the product
Retriever/VectorStore. No embedding sleep, forced slot acquisition or synthetic
503 is injected. Therefore a busy 503 is the real application admission failure,
but its frequency includes this embedding/corpus choice and cannot be compared
as production encoder throughput. No embedding model weights are fetched.

Because the adapter passes its own Retriever and StudyRuntime into the product
app, the product lifespan does not read the two lane settings itself. `perf_app`
therefore parses them with the product's `bounded_setting` and constants (an
out-of-range value fails startup, as in the product), builds the Retriever with
`query_concurrency` and the StudyRuntime with `concurrency`, and logs one
`PERF_FACTORY ... retrieval_concurrency=N; run_concurrency=M` line from the
constructed objects. The runner refuses to measure unless that line matches the
requested point and records it as `effective_agent_lanes`.

`CountingRetriever` subclasses the product Retriever and only counts each
`search()` outcome (`ok`, `busy_503`, `index_changed_409`, `index_not_ready_409`,
`error`). Java maps every non-200 retrieval to `RETRIEVAL_UNAVAILABLE`, and the
Tutor/Study tools see a generic failure, so only these server-side counters can
separate busy from snapshot-change rejections on S2–S4. They are exposed on an
eval-only, HMAC-signed loopback route `POST /internal/perf-p0/retrieval-outcomes`
and snapshotted before and after each group; the snapshots are outside the group
wall time. A request whose client timed out but which the server finishes later
is counted in the next snapshot.

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
  or frozen Tutor source is edited.
- S4: `DelayedStudyMock` sleeps once per `flashcards` decision inside the Run
  lane, then delegates to the product Study `MockProvider`. A normal Run makes two
  decisions. Logs attest each wrapper was actually used.

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
schema v2 records cleanup separately from operation/turn latency, while drained
wall time still includes it. An undrained turn stops further admission and
subsequent groups.
Do not interpret a timeout as an absent or successful observation.

Failed S4 attempts drain the same way: `CANCEL` the own Run and poll `READ` to a
terminal state within eight seconds. If the `GENERATE_CARDS` response was lost
(transport error, no envelope), the Run cannot be named; that attempt is recorded
as undrained and stops admission. Cancel is terminal in PostgreSQL immediately;
the worker lane is released at its next guard, at most one Mock decision later.

- `result.json`: schema/config, label, Git SHA + dirty/source drift checks, CPU
  model/count/affinity/cgroup limits, RAM/kernel/architecture, Python/Java/Docker/
  Compose versions, jar/file/image hashes, corpus/config fingerprints, stages,
  warmups, per-group counts, error rate and throughput.
- `requests.jsonl`: one row per logical attempt, with warmup flag, latency, HTTP
  request/poll counts, last operation HTTP status, error category and Retry-After.
  No credentials, prompts, answers or arbitrary error payloads are written here.
  Schema v2 also records all response status counts, HTTP sends (including sends
  without a response), separate cleanup time, turn time and relative wall offsets.
  `http_status_counts` remains the legacy **last response per logical operation**
  histogram; `http_response_status_counts` counts actual responses and can exceed
  operation count for Tutor polling. Cancel
  cleanup requests are counted separately and do not overwrite the error status.
- Schema v3 (this revision) keeps every v2 field and denominator and adds:
  `failure_class` per failed row and `failure_classes` per group
  (`retrieval_busy_503` = direct S1 503 `Retrieval busy`;
  `evidence_index_changed_409` = direct S1 409 `Evidence index changed`;
  `other_unexpected` = every other failure, including 409 `Evidence index not
  ready` and Java-mediated retrieval failures; the three always sum to `failed`);
  `agent_retrieval_outcomes` per group (server counters above); for S3/S4
  `queue_ms` (submit start → first poll seeing `running`), `execution_ms` (that
  poll → poll seeing terminal) and `running_observed`, with success-only P50/P95
  and a `running_unobserved` count when a turn/Run finished between polls (no
  boundary is invented; resolution is one 0.1 s poll plus one Java round trip, and
  S4 queue time includes the dispatcher's ≤1 s re-poll); `run_id`/`run_status` for
  S4; config fields `agent_retrieval_concurrency`, `agent_run_concurrency`,
  `retrieval_admission`, `study_run_lanes`, `tutor_worker_model` and
  `study_mock_task` (the misleading v2 `retriever_lock` field is removed); and
  `effective_agent_lanes`. The legacy `retrieval_busy_503` count and the
  `undrained_tutor` field name are retained (the latter now also covers S4).
- `REPORT.md`: concise group table (three failure classes, server busy/changed,
  all/success latency, queue/execution split) and NOT_RUN list. P50/P95 use nearest rank in
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
  --sha "$(git rev-parse HEAD)" --check-inputs
agent-service/.venv/bin/python eval/perf-p0/verify.py .data/perf-p0/dev-busy \
  --sha "$(git rev-parse HEAD)" --check-inputs --require-busy
```

Expected 503s never turn into a synthetic pass: `--require-busy` fails unless S1
actually observed `503 / Retrieval busy` and `Retry-After: 1`. For schema v3 it
first fails if the configured matrix has no S1 level above
`agent_retrieval_concurrency`: at most that many searches hold a slot, so busy is
impossible at or below it (the condition is necessary, not sufficient; with fast
hash384 searches the slots may never all be held at once). The development busy
example uses c=8 against the default 4 slots; add `--retrieval-concurrency 1` to
reproduce single-slot admission. If
a machine cannot reproduce busy within the bounded smoke, retain that observation
honestly. The harness never rebuilds the index during measurement, so any
`evidence_index_changed_409` is unexpected for this workload and makes the point
ineligible for comparison until explained.

Normal completion, errors, Ctrl-C and SIGTERM run owned cleanup, verify no
containers/volumes/networks remain and retain failure logs. Use `--run-deadline` (default 1200s), or verify and SIGTERM the exact recorded
runner PID/start ticks; leave 600s between the internal and outer deadlines for
cleanup. The generic supervisor has only five seconds of kill grace: Ctrl-C of
that supervisor can interrupt teardown. Never suspend a sudo child or kill
processes by broad name.
After SIGKILL/host failure, remove only the recorded Compose projects with:

```bash
python3 eval/perf-p0/cleanup.py .data/perf-p0/dev-health
```

Emergency cleanup requires the same output/worktree and an explicit ownership
journal. It refuses copied or legacy results, including old P0 results without
that journal. It needs no original password and removes only owned resources,
not application processes. Stop surviving Java/Agent children via the original
supervisor/session, verifying each recorded PID/start ticks and that its command belongs to this
output directory first.

## Targeted verification

```bash
agent-service/.venv/bin/ruff check eval/perf-p0
agent-service/.venv/bin/ruff format --check eval/perf-p0
bash -n eval/perf-p0/run.sh
python3 scripts/dev/run_check.py --name perf-harness-unit \
  --output .data/perf-p0/checks --timeout 120 -- \
  agent-service/.venv/bin/python eval/perf-p0/deterministic_tests.py
```

Deterministic suite at this revision: **51 tests** (29 P11-A plus 22 Step 6 lane
tests in `test_lanes.py`). Self-tests use simulated HTTP only to verify harness accounting/protocol rules;
they do not replace the fresh Java→Python→MySQL/PostgreSQL smoke above. Java addon
compilation and actual wrapper use are checked by each service smoke. No product
or shared Study code changed, so Agent full pytest, frontend build and product
Java suites are NOT_RUN for this harness-only change. Existing development and
Tutor frozen hashes can be checked without rewriting any manifest.

Schema v1/v2 historical evidence is read-only and remains verifiable at its own
recorded SHA, rather than current HEAD. Schema v1 latency includes cancellation
cleanup. Do not compare it directly with v2/v3 operation/turn latency. Schema v1/v2
runs measured the pre-Step-6 single retrieval lock; never pair them with v3 lane
results as a before/after comparison. `verify.py`
now uses independent metric recomputation and rejects missing matrix points,
failed/missing warmups, nonfinite metrics, raw SHA/label drift and empty groups;
its checks stay active under `python -O`. Run the guarded deterministic suite
for P11-A; it forbids IP sockets, DNS and service subprocesses. No fresh stack or
load validation has been performed for the reviewed v2 harness.
