# P11-A framework review

Conclusion: **PASS for deterministic framework review and preparation**. Formal
rental measurements, reviewed-harness service integration and real Provider
performance are **NOT_RUN**. This review started from clean Perf P0 `5b411a6`
on main `300be51515867f7ece4f3a9224a484e825219ee0`, fetched before work. Changes
are confined to `eval/perf-p0/`; no product source, workflow, authority, budget,
worker, retrieval lock or frozen evaluation identity is changed.

P11-A actual business load: **0**. Service starts/restarts: **0**. Real Provider
calls: **0**. Existing services, databases and other worktrees are not touched.
The rental plan is [P11_RENTAL_PLAN.md](P11_RENTAL_PLAN.md); it requires separate
execution approval on a disposable machine.

## Findings and fixes

| Finding in historical harness | Review change | Deterministic evidence |
|---|---|---|
| Log collection and Compose down shared a try block, so log failure skipped teardown | Visit every owned child/project; attempt down independently; preserve log errors and fail on cleanup/resource inspection failures | Simulated log/child-stop failures still visit both owned projects; unowned collision triggers no cleanup |
| Emergency cleanup trusted only project namespace, accepted duplicate roles and could clean unowned preflight-collision names | Require exact infra/pg pair, same worktree/output and explicit persisted ownership journal; record ownership before any up command | Mocked emergency cleanup refuses copied/duplicate records and targets only journal-owned projects |
| Verifier trusted the present groups and shared the runner's calculator | Independently recompute counts/nearest-rank/throughput; require full configured matrix, successful warmups, raw row SHA/label, finite timings, request caps, stop conditions and correlated busy proof | Sixteen malformed-bundle mutations, busy/Retry-After correlation and known twenty-sample quantiles; checks also run under Python -O |
| HTTP sends were counted only after a response; non-JSON 429/503 and arbitrary code fields were ambiguous | Count sends before awaiting, record actual response histogram separately from legacy last-response histogram, retain status in failures and bound structured error fields | Non-JSON 429/503, HTTP-200 business errors, malformed envelopes, response-free timeouts, no retry |
| Whole Tutor timing included Session creation and failed-operation cancel cleanup | Schema v2 separates whole operation, turn-submit-to-observed-terminal time and cleanup; wall denominator still includes client setup/drain/cleanup | Controlled clock excludes Session creation from turn time; queued acceptance is not completion; terminal failure stays failure; cleanup time separates from operation latency |
| A cancelled coroutine could suppress cancellation and return success; undrained work could admit more operations in that group | Check expired deadline even after return; stop further admission when cleanup cannot drain | Suppressed-cancellation and undrained-work cases remain failures |
| Rental checks inspected only root cgroup files; full-run timeout could be shorter than teardown grace | Read visible v2 ancestors, fail closed on unknown limits; record package versions/resource limits/PIDs/start ticks; add internal execution deadline and document outer cleanup grace | Synthetic nested quota/unknown/unlimited-root checks; no host settings are changed |

The reviewed runner also checks QA Evidence IDs/revision and Tutor allowed inline
citation IDs. These are protocol fences, not a semantic answer-quality score.
The Mock providers and injected latency wrappers continue to delegate to the
same product implementations. Java still owns auth/course/Evidence authority;
Python/PostgreSQL owns Tutor state. No new persistence tables or cross-service
writes are introduced.

## Measurement contracts

- S1: one signed direct retrieval request; success requires fenced nonempty hits.
  It bypasses Java and Study Run orchestration.
- S2: one authenticated Java QA operation, including retrieval and saved answer;
  success requires current allowed Evidence. QA 429 and retrieval failure remain
  errors. The existing default rate limit is unchanged.
- S3: fresh Session, submit a turn and poll to supported completed answer. Its
  turn timer starts before the turn POST and ends at observed terminal state,
  including queueing and polling (not a server-only execution timer).
- Closed-loop concurrency bounds in-flight logical operations. One warmup per
  scenario is excluded. No automatic HTTP retries, redirects or backoff; Tutor
  polling is completion observation. Admission duration stops new work and
  drains in-flight attempts with bounded timeout/cancellation cleanup.
- Error rate is failed/attempted. Successful throughput is completed successful
  logical operations/drained group wall seconds. Report all/success/failure
  nearest-rank P50/P95 independently. Fast rejects can lower all-attempt P95.
  Schema v2 has full-precision wall seconds and relative attempt offsets.
- `http_status_counts` is the last response per logical operation (legacy field),
  whereas `http_response_status_counts` counts every response. A timed-out Tutor
  operation may have last HTTP 200; that does not change its failed outcome.
- Inputs record SHA/clean state, CPU/affinity/memory/visible cgroups/resource limits,
  Python distributions/uv/Java/Docker/Compose, image/jar/config/file/corpus hashes.
  These are reproducibility inputs, not third-party attestation. Visible cgroup
  limits cannot prove the absence of hidden host quotas or noisy neighbors.

## Historical 503 attribution (read-only)

Historical Perf P0 clean SHA: `5b411a6905fbc0785f36f8e386230be511a1ea40`.
The original `DEV_SMOKE_NOT_RESUME` files remain local at
`.data/perf-p0/final/{health,busy}/`; no old result, failure or raw row is edited.
Read-only verification recovers S1 c=1 **64/64 success**, and c=8 **61/64 failed**
with exactly `503 Retrieval busy` plus `Retry-After: 1`. Health has three measured
successful operations for each of S1/S2/S3. These are tiny 4-CPU development
samples with hash384 embeddings and one synthetic course, not formal baselines
or resume metrics. They do not establish capacity of the reviewed harness SHA.

| Historical file | SHA-256 |
|---|---|
| `health/result.json` | `3467741f80dea25705f9ba7ecfae9152d00fcbe7c5792f07abe699a7fae97530` |
| `health/requests.jsonl` | `86aecbe6f469be31f275ba0220267edd513248d79703a39081cedb0f371be363` |
| `busy/result.json` | `0a7f1e557ecd2c828a879baccdad1ad6b01e1b34cbbee2c492a56bc156f1b168` |
| `busy/requests.jsonl` | `6e3dcc8f5ae896616716d135264653c4a3f7202a7f3fbe9815bdbe2699ec9f63` |

`Retriever.search()` acquires an in-process `threading.Lock` with
`blocking=False` before snapshot lookup, embedding and PostgreSQL search; failed
acquisition raises BusyError. `app.py` maps precisely that exception to busy 503
and Retry-After:1. The lock spans the whole admitted search and is shared with
index APPLY; PLAN/DELETE have different admission behavior. One Uvicorn worker
means one such lock across courses/owners in that Retriever instance. Failures need not correspond to one simultaneous wave:
closed-loop rejected clients immediately issue their next attempt, so 61/64 is
not a fixed 7/8 rejection law.

This establishes an application admission limit. The rejected attempts have not
reached vector SQL or embedding. Admitted lock hold time may still depend on
PostgreSQL, CPU/embedding and scheduling; the historical sample lacks causal
resource telemetry. Database saturation, CPU/memory exhaustion, driver saturation
and index-size/real-encoder effects are **unverified hypotheses**, not conclusions.
The older Phase E 90/31 count describes whole Study Runs failing at SEARCH,
not this S1 per-request denominator. No performance optimization is made here.

P11-B should measure successful latency/throughput and busy fraction against
per-core CPU, steal/throttling, memory, disk and PG waits under identical input
fingerprints. Check whether serial admitted service time changes with resources,
whether the driver is saturated and whether any index sync overlaps measurement.
The unchanged Mock/hash384 workload cannot answer real-encoder/real-Provider
performance questions. Any later concurrency-mechanism change needs a separate
approved task and paired before/after evidence.

## Reproduce review without services

Use existing locked Python dependencies. All tests run with an audit hook that
rejects IP sockets, DNS and non-read-only-Git subprocesses; HTTP uses in-memory
MockTransport, resource cleanup uses subprocess mocks and hardware tests use
synthetic files. No existing stack or database is needed.

```bash
agent-service/.venv/bin/ruff check eval/perf-p0
agent-service/.venv/bin/ruff format --check eval/perf-p0
bash -n eval/perf-p0/run.sh
python3 scripts/dev/run_check.py --name p11-a-unit \
  --output .data/p11-a/checks --timeout 120 -- \
  agent-service/.venv/bin/python eval/perf-p0/deterministic_tests.py
python3 scripts/dev/run_check.py --name p11-a-unit-optimized \
  --output .data/p11-a/checks --timeout 120 -- \
  agent-service/.venv/bin/python -O eval/perf-p0/deterministic_tests.py
```

Deterministic suite: **29 passed** in normal and optimized modes (including the
original eleven harness tests with strengthened provenance fixtures). Historical
read-only checks, when original local evidence is available:

```bash
agent-service/.venv/bin/python eval/perf-p0/verify.py \
  .data/perf-p0/final/health --sha 5b411a6905fbc0785f36f8e386230be511a1ea40 --check-inputs
agent-service/.venv/bin/python eval/perf-p0/verify.py \
  .data/perf-p0/final/busy --sha 5b411a6905fbc0785f36f8e386230be511a1ea40 --require-busy --check-inputs
```

Historical v1 records remain v1; the checker does not upgrade them or attribute
them to current HEAD. Python -O does not disable verification. Current development
identity and Tutor frozen file hashes are checked read-only, not re-registered.
Local command/exit metadata is retained under `.data/p11-a/checks/`.

NOT_RUN: any new real-service/load matrix, rented machine or paid/real Provider;
reviewed schema-v2 live-stack cleanup/HTTP integration; optional source-built
MinIO bootstrap; full Agent DB/frontend/Java suites locally (no product changes).
CI status is reported from GitHub for the Draft PR, not inferred from these tests.
Passing P11-A prepares the independent-machine experiment; it does not execute
P11-B, validate real-model quality or establish a performance improvement.
