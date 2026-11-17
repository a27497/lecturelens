# P11 / L2 independent-server measurement plan

Status: **prepared, NOT_RUN**. Preparation performs no service startup, business
load, cloud rental or real Provider calls. Execution below requires a separately
approved window on a disposable independent machine. Do not run this plan on the
shared development server.

L2 revision: the harness now targets the Step 6 concurrency lanes
([AGENT_CONCURRENCY.md](../../docs/AGENT_CONCURRENCY.md)), schema v3. The goal
is to measure success rate, throughput, P50/P95 and the expected busy rejections
at the target concurrency, then decide whether `AGENT_RETRIEVAL_CONCURRENCY=4` and
`AGENT_RUN_CONCURRENCY=2` fit. "Defaults are adequate, no change" is an
acceptable outcome.

## Machine and spending envelope

- Linux x86-64, at least **16 logical CPUs / 60 GB usable RAM**; select a 16-vCPU /
  64-GB instance with local SSD and enough free disk for dependencies, Docker and
  retained per-run logs (100 GB free is a planning allowance, not a benchmark).
  No GPU or hosted model account is needed for this Mock mechanism baseline.
- Record vendor/SKU, dedicated/shared CPU policy, region, kernel, storage type,
  Docker version, throttling/steal time and background processes. Use one machine
  for a comparison. Avoid colocated workloads. Visible cgroup v2 ancestor limits
  and CPU affinity must pass the runner's hardware check; unknown limits fail
  closed. Limits hidden by a host/container namespace still require operator
  confirmation against the rental specification.
- Obtain an hourly quote and an approved spending/time cap **before** ordering.
  Budget = quoted hourly rate × approved maximum hours (see the machine-hour
  estimate below) + storage/network/tax. There is no vendor price claim here. Use
  hourly billing, a disposable disk, billing alerts and a provider-side automatic
  shutdown deadline. Record expiry in UTC. Stop provisioning if dependency
  bootstrap consumes its agreed budget; do not silently extend the rental. Delete
  the instance/disk after exporting redacted evidence. No cloud account
  credentials belong in this repository.

## Fixed workload

Use a clean committed PR HEAD, locked dependencies and the same image IDs. This
harness is **Mock only**: hash384 embeddings, one generated short synthetic
course, one owner/revision shared by clients, top_k=8, one Uvicorn process, the
product query slots / index APPLY lock / Run lanes / budgets, and the experimental
Tutor's single worker. A fresh Tutor or Study Session is created per operation.
Model delay is 150 ms per Mock decision: QA in Java, every Tutor decision and
every flashcard decision in Python. This is a controlled injected delay, not
observed real-model latency or production semantic-encoder throughput.

What each lane setting can affect, which keeps the matrix small:

| Setting | S1 direct retrieve | S2 Java QA | S3 Tutor | S4 Study Run |
|---|---|---|---|---|
| `AGENT_RETRIEVAL_CONCURRENCY` | yes: up to c concurrent searches | yes: up to c concurrent searches via Java | at most 1 Tutor search at a time (single worker) | at most `AGENT_RUN_CONCURRENCY` (≤4 here) concurrent Run searches |
| `AGENT_RUN_CONCURRENCY` | no | no | no (separate Tutor runtime) | yes: lanes hold a Run through both Mock decisions |

So more query slots can only change S1/S2 here, and more Run lanes only S4.

## Lane configurations and matrix

| Config | `AGENT_RETRIEVAL_CONCURRENCY` | `AGENT_RUN_CONCURRENCY` | Role |
|---|---:|---:|---|
| A | **4** | **2** | Product defaults |
| B | 8 | 2 | Retrieval control. Upward, because the L2 question is whether 4 slots reject work that a 16-vCPU host could serve; 8 shows whether extra slots raise successful throughput/P95 or only turn fast 503s into slower successes. Single-slot behavior is already covered by historical evidence. |
| C | 4 | 4 | Run control. Upward, because a 150 ms × 2 Mock Run holds a lane ≥300 ms and c≥4 queues behind 2 lanes; 4 shows whether lanes are the S4 bottleneck. 1 would reproduce the pre-Step-6 single worker. |

Each invocation is one fresh stack and runs the concurrency ladder **1 → 4 → 8 →
16** in that fixed order for each listed scenario, scenarios in the listed order.

| Invocation | Config | Scenarios | Stop per group | QA policy | Points |
|---|---|---|---|---|---:|
| `a-qa` | A | S1, S2, S3 | 60 s admission + drain, 60 s op timeout | raised to 100000/owner/minute | 12 |
| `a-run` | A | S4 | same | not on path | 4 |
| `b-qa` | B | S1, S2 | same | raised to 100000/owner/minute | 8 |
| `c-run` | C | S4 | same | not on path | 4 |

**Measurement points: 28** (scenario × config × concurrency). Each point has
**3 repetitions** on fresh stacks: **84 point-repetitions** in **12 invocations**
(4 per repetition), plus one unmeasured shakedown invocation.

- Pairing: `b-qa` vs `a-qa` compare S1/S2 at the same scenario/ladder position
  (S3 runs after S2 in `a-qa`, so it cannot affect them). `c-run` vs `a-run`
  compare S4 on otherwise identical fresh stacks. S3 is measured only at the
  defaults, as the Tutor single-worker queue/execution baseline.
- Trade-off: the earlier plan used one stack per (scenario, c). Running the
  ladder in one stack cuts stack bootstraps 4× (see the estimate) at the cost of
  order effects (the database grows with saved QA results, Sessions and decks).
  The order is identical in every repetition and configuration, so paired
  comparisons share it; do not compare a c=16 group with a c=16 group from a
  different ladder position.
- The raised QA limit is a harness setting on the disposable stack, not a product
  change; the existing default (10/owner/minute) would make S2 measure only 429s.
  The owner's approval of the L2 window must include it. Without that approval,
  drop S2 (`a-qa` = S1,S3; `b-qa` = S1; 20 points) and record S2 as NOT_RUN.
- Optional, not counted above: the earlier **default-policy** S2 row (config A,
  `--requests 64 --qa-per-minute 10`, c=1/4/8/16, 3 invocations). It measures the
  rate-limit envelope, not the lanes. Never combine its denominator with the
  raised-limit rows.

Every group is preceded within its invocation by one excluded warmup per scenario;
this consumes the real QA counter. Do not clear counters in-place. Window
boundaries and warmup consumption affect success counts.

S1 attempts are signed HTTP retrieval requests, not whole Study Runs. S2 success
requires a saved QA answer with current allowed Evidence. S3 success requires a
supported **completed** turn with allowed inline citations. S4 success requires a
**succeeded** flashcard Run whose events include `deck_created` with at least one
card. S3/S4 include queueing and completion polling; schema v3 reports
whole-operation latency, submit-to-terminal `turn_latency_ms`, and the
client-observed split `queue_ms` / `execution_ms` (resolution: one 0.1 s poll plus
one Java round trip; S4 queue includes the Run dispatcher's ≤1 s re-poll).
Cancellation cleanup has its own time and remains in the drained wall-time
denominator.

## Machine-hour estimate

Nothing here was measured on the rental machine. Planning inputs:

| Input | Planning value | Basis |
|---|---:|---|
| One-time host preparation and first online bootstrap (packages, Maven/uv dependencies, image pulls, version record) | 45 min | Allowance; dependency downloads are not timed in this repository |
| Shakedown invocation (config A, S1–S4, c=1, `--requests 3`), verified, before the matrix | 10 min | 8 min overhead + ~2 min groups |
| Fixed overhead per invocation (offline package, infra + PostgreSQL up, Java + Agent start, synthetic course, attestation, logs, owned teardown, `verify.py`, export) | 8 min | The CI job "MySQL migrations and Mock AI E2E" runs the same `Smoke` lifecycle on a hosted runner in 244–313 s (median ≈290 s, last 12 successful CI runs, 2026-11). 8 min ≈ 1.6× that median for the extra compile/fingerprint/log steps |
| Warmups per invocation | 1 min | One operation per scenario |
| One measured group | 70 s typical, 130 s upper | 60 s admission, then drain: an attempt admitted at the end of the window can take the 60 s operation timeout plus the 8 s cancel/drain window (128 s) |
| Final export, checksum manifest, instance/disk deletion | 15 min | Allowance |

Per repetition: 4 invocations × (8 + 1) min = 36 min, plus 28 groups × 70 s =
32.7 min (typical) or × 130 s = 60.7 min (upper) → **68.7 min typical, 96.7 min
upper**.

Three repetitions: 206 min typical, 290 min upper. Adding one-time preparation,
shakedown and final export (45 + 10 + 15 = 70 min):

- typical: 206 + 70 = **276 min ≈ 4.6 machine hours**
- upper: 290 + 70 = **360 min = 6.0 machine hours**

Request an approved cap of **8 machine hours**: the 6.0 h upper bound plus 25%
(1.5 h) for re-running failed invocations = 7.5 h, rounded up. The optional
default-policy S2 row adds 3 × (8 + 1 + 4 × ~0.5) ≈ 33 min typical and
3 × (9 + 4 × 130 s) ≈ 53 min upper; run it only if at least 55 min remain under
the cap after the core matrix (6.0 h + 0.9 h = 6.9 h upper without re-runs). If the S2 approval is absent, the 20-point matrix needs
20 groups per repetition: upper 3 × (36 + 43.3) + 70 = 308 min ≈ 5.1 h. For
comparison, the earlier one-stack-per-point layout would need 84 invocations ×
9 min = 12.6 h of overhead alone.

Stop the rental at the cap even if points remain; leave them NOT_RUN.

## Execute only on the approved rental machine

Install Java 21 + javac, Python >=3.12, uv, Docker Compose >=2.24.4, Bash and
FFmpeg. Public dependency bootstrap is allowed; provider credentials are not.
Resolve/bootstrap once, record actual versions/image IDs, then use `--offline`
for repetitions. Do not upgrade dependencies between trials. If CI source-built
MinIO is needed, use `--build-minio` consistently and record its different image
fingerprint; this bootstrap alternative remains untested.

Shakedown (not a measurement point):

```bash
python3 scripts/dev/run_check.py --name "l2-shakedown" \
  --output .data/l2-rental/checks --timeout 2400 -- \
  bash eval/perf-p0/run.sh --offline --profile rental --scenarios S1,S2,S3,S4 \
  --concurrency 1 --requests 3 --timeout 60 --mock-delay-ms 150 \
  --qa-per-minute 100000 --retrieval-concurrency 4 --run-concurrency 2 \
  --run-deadline 1800 --output .data/l2-rental/shakedown
```

Without the raised-QA approval, use `--scenarios S1,S3,S4 --qa-per-minute 10`
for the shakedown and the fallback lines in the matrix below.

The matrix, for rep=1,2,3 in this order (each line is one fresh invocation):

```bash
# Not executed during preparation. Requires the approved window.
run_point() {  # name scenarios retrieval run qa
  python3 scripts/dev/run_check.py --name "l2-$1-r${rep}" \
    --output .data/l2-rental/checks --timeout 3600 -- \
    bash eval/perf-p0/run.sh --offline --profile rental --scenarios "$2" \
    --concurrency 1,4,8,16 --seconds 60 --timeout 60 --mock-delay-ms 150 \
    --retrieval-concurrency "$3" --run-concurrency "$4" --qa-per-minute "$5" \
    --run-deadline 3000 --output ".data/l2-rental/$1-r${rep}" &&
  agent-service/.venv/bin/python eval/perf-p0/verify.py \
    ".data/l2-rental/$1-r${rep}" --sha "$(git rev-parse HEAD)" --check-inputs
}
for rep in 1 2 3; do
  run_point a-qa  S1,S2,S3 4 2 100000 &&
  run_point a-run S4       4 2 10 &&
  run_point b-qa  S1,S2    8 2 100000 &&
  run_point c-run S4       4 4 10 || break
done
# Fallback without the raised-QA approval (20 points; S2 recorded NOT_RUN):
#   run_point a-qa S1,S3 4 2 10 && run_point a-run S4 4 2 10 &&
#   run_point b-qa S1    8 2 10 && run_point c-run S4 4 4 10 || break
```

The sequence is bounded (12 invocations, no model calls) and stops at the first
failed invocation or verification instead of continuing; inspect the failure
before any re-run. `--qa-per-minute` is irrelevant for the S4-only invocations and keeps
the product default. The internal deadline (3000 s) covers the 8 min overhead and
at most 12 groups × 130 s (2100 s total); the outer timeout exceeds it by 600 s for cleanup.
Bootstrap failures or timeouts are retained, not relabeled as performance
observations. A failed invocation may be re-run once as a new output directory
inside the cap; keep both.

## Observation, stops and cleanup

Start read-only observations before warmup, retaining UTC timestamps through
cleanup. On this disposable machine, use `vmstat 1`, `iostat -xz 1` and
`pidstat -dur 1`; keep their tool versions/interval/overhead identical in paired
trials. Capture Docker stats only for project names in this run's `result.json`
and Java/Agent processes in its recorded `children`. Record per-core utilization,
CPU steal/throttling, RSS/available memory, swap/OOM, disk I/O, filesystem free
space and PostgreSQL connections/query waits using read-only observations of
the **owned** instance (config C adds ~6 PostgreSQL connections for the two extra
lanes). Never inspect other worktree databases or user data. Include driver
CPU/event-loop saturation: closed-loop rates may reflect the client as well as
the service. The framework does not automatically prove a hardware bottleneck or
attribute CPU time to embedding/SQL/slot hold time.

Stop a point if it exceeds the internal deadline, cleanup cannot drain a Tutor
turn or Study Run, ownership/revision checks fail, evidence cannot be verified,
the effective lanes differ from the requested configuration, memory/disk
approaches the operator's approved safety threshold, OOM occurs, or unexpected
external network/provider activity appears. A run with lost telemetry or a
changed fingerprint is ineligible for comparison. Expected busy 503/QA 429 is a
reported failure, not by itself evidence of hardware exhaustion. Any
`evidence_index_changed_409` (client or server) is unexpected because nothing
rebuilds the index during measurement; mark the point ineligible until explained.
Do not retry, add sleeps/backoff, raise workers, alter slots/locks or relax
budgets to improve numbers.

For an early stop, verify `runner_pid` and `/proc/<pid>/stat` start ticks against
the recorded `runner_start_ticks`, then SIGTERM that exact runner and allow it
to finish cleanup. Do not Ctrl-C the outer supervisor during cleanup: its generic
five-second kill grace is shorter than full stack teardown. Do not kill by
process name. An outer forced timeout/host failure can still interrupt cleanup;
verify each recorded child PID/start tick before stopping surviving children and
use `cleanup.py OUTPUT` for Compose resources. Emergency cleanup accepts only
the same output/worktree's explicit ownership journal; a copied/legacy result
is refused. Treat unresolved cleanup as a failed run and inspect owned labels
before any manual removal. No cleanup step deletes other projects or uses prune.

Verify each completed result before proceeding:

```bash
agent-service/.venv/bin/python eval/perf-p0/verify.py OUTPUT \
  --sha "$(git rev-parse HEAD)" --check-inputs
# For a-qa/b-qa, --require-busy may be added: it first requires an S1 level above
# the configured slots (true for 8/16 vs 4, and 16 vs 8), then an observed
# 503 Retrieval busy with Retry-After: 1. Absence of busy is a result, not a defect.
```

Export `result.json`, `requests.jsonl`, reports, redacted logs and telemetry with
a checksum manifest. Confirm no owned containers/volumes/networks or application
children remain before releasing the rental. Preserve failures and raw attempts.

## Interpretation and decision

For each repetition report attempted/success/failed counts, the three failure
classes (`retrieval_busy_503`, `evidence_index_changed_409`, `other_unexpected`),
the server-side `agent_retrieval_outcomes` (needed for S2–S4, where Java collapses
busy/changed into `RETRIEVAL_UNAVAILABLE`), 429s and Retry-After, successful and
attempted operations/s, all/success/failure P50/P95 and timeouts. S3/S4
additionally report submit-to-terminal latency, `queue_ms` / `execution_ms`
P50/P95 and `running_unobserved`. Show each repetition and its spread; do not
select only the best. Warmups, admission window, operation timeout, polling,
cleanup/drain time and clock resolution must be reported. Do not pool per-run
percentiles; recompute pooled percentiles from eligible raw rows only when the
conditions are identical.

Pre-declared decision rule (three repetitions, compare medians and the min–max
range per point):

- Retrieval (`b-qa` vs `a-qa`, S1 and S2 at c=8/16): keep 4 unless config B raises
  S2 **successful** operations/s beyond the non-overlapping repetition range
  **and** does not worsen S2 successful P95 beyond that range, with host CPU not
  saturated. A lower S1 busy count alone is not a reason to change: busy is the
  intended backpressure, and fewer fast rejections can raise all-attempt P95.
- Run lanes (`c-run` vs `a-run`, S4 at c=4/8/16): keep 2 unless config C cuts S4
  `queue_ms` P95 and raises successful Runs/s beyond the repetition range without
  raising `execution_ms` P95 or failures beyond it. `queue_ms` covers only Runs
  whose `running` state a poll observed; compare it only when `running_unobserved`
  is under 5% of successful Runs in both configurations. Otherwise replace the
  `queue_ms` condition with successful `turn_latency_ms` P95; the throughput,
  `execution_ms` and failure guards still apply. Mock execution holds a lane for
  injected delay, not real model I/O; any change still needs the provider-side
  rate-limit caveat in AGENT_CONCURRENCY.md.
- At most two parameter changes come out of L2, each as a separate product change
  with its own review. If neither rule fires, the deliverable is "defaults
  adequate for this workload" with the data table.

Freeze hardware/SKU, image and dependency fingerprints, corpus/text/chunk hashes,
query, embedding, injected delay, owner/course topology, lane sizes, worker
counts, limits, initial empty databases, warmup, stop conditions and telemetry
overhead. Record both source SHAs and the exact diff for any later optimization.
Future optimization is a separate task: rerun the same matrix, account for
error-rate changes, compare successful P95/throughput, and report all failures.
A lower all-attempt P95 caused by more fast rejections is not an improvement.
Schema v1/v2 results measured the pre-Step-6 single lock (and v1 latency included
cancel cleanup); never pair them with schema v3 lane results.

Resume claims require approved independent-machine execution, clean source,
complete repeatable evidence and an honest workload/mode/hardware description.
A verified before/after claim additionally needs both measured baselines under
the same conditions. Mock/hash384 results may support only clearly qualified
mechanism/admission claims, never real-provider latency/quality, semantic
retrieval performance, teaching quality or general production capacity.
Historical `DEV_SMOKE_NOT_RESUME` (including 61/64 busy responses under the old
single lock), single tiny samples, policy-limited throughput and unexecuted plans
are development diagnosis only. No performance number is prefilled by this plan.
