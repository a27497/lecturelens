# P11 independent-server measurement plan

Status: **prepared, NOT_RUN**. P11-A performs no service startup, business load,
cloud rental or real Provider calls. Execution below requires a separately
approved P11-B window on a disposable independent machine. Do not run this plan
on the shared SameScale development server.

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
  Budget = quoted hourly rate × approved maximum hours + storage/network/tax.
  There is no vendor price claim here. Use hourly billing, a disposable disk,
  billing alerts and a provider-side automatic shutdown deadline. Record expiry
  in UTC. Stop provisioning if dependency bootstrap consumes its agreed budget;
  do not silently extend the rental. Delete the instance/disk after exporting
  redacted evidence. No cloud account credentials belong in this repository.

## Fixed workload and matrix

Use a clean committed PR HEAD, locked dependencies and the same image IDs. This
harness is **Mock only**: hash384 embeddings, one generated short synthetic
course, one owner/revision shared by clients, top_k=8, one original Uvicorn/Tutor
worker, original retrieval lock and budgets. A fresh Tutor Session is created
per operation. Model delay is 150 ms per decision in this planned matrix, QA
only in Java and every Tutor decision in Python. This is a controlled injected
delay, not observed real-model latency or production semantic-encoder throughput.

| Experiment | Path | Concurrency | Stop condition per point | QA policy |
|---|---|---|---|---|
| Default policy baseline | S2 Java QA | 1 / 4 / 8 / 16 | 64 logical attempts | enabled, original 10/owner/minute |
| Mock mechanism baseline | S1 pure retrieve | 1 / 4 / 8 / 16 | 60 s admission, drain | default (not on this direct path) |
| Authorized test configuration | S2 Java QA | 1 / 4 / 8 / 16 | 60 s admission, drain | enabled, 100000/owner/minute **only if separately approved** |
| Mock mechanism baseline | S3 Tutor completion | 1 / 4 / 8 / 16 | 60 s admission, drain | original Tutor budgets; no QA quota change needed |

Run **three independent repetitions** of every chosen point, each with a fresh
stack/database and new output path. Keep the scenario/order fixed in paired
before/after trials. Every point has one excluded warmup; this consumes the real
QA counter. Do not clear counters in-place. The default-policy request cap
prevents a long tight loop of fast 429s; it is a policy/rejection experiment,
not a sustained capacity figure. Window boundaries and warmup consumption affect
success counts. Never combine its denominator with the raised-limit experiment.
If the raised limit is not approved, leave that matrix explicitly NOT_RUN.

S1 attempts are signed HTTP retrieval requests, not whole Study Runs. S2 success
requires a saved QA answer with current allowed Evidence. S3 success requires a
supported **completed** turn with allowed inline citations, not HTTP acceptance.
S3 includes queueing and completion polling. Schema v2 reports whole-operation
latency and submit-to-observed-terminal `turn_latency_ms` separately; cancellation
cleanup has its own time and remains in the drained wall-time denominator.

## Execute only on the approved rental machine

Install Java 21 + javac, Python >=3.12, uv, Docker Compose >=2.24.4, Bash and
FFmpeg. Public dependency bootstrap is allowed; provider credentials are not.
Resolve/bootstrap once, record actual versions/image IDs, then use `--offline`
for repetitions. Do not upgrade dependencies between trials. If CI source-built
MinIO is needed, use `--build-minio` consistently and record its different image
fingerprint; this bootstrap alternative remains untested by P11-A.

The following is one point. Repeat it for c=1,4,8,16 and rep=1,2,3 with unique
names, using the table's scenario/stop/policy settings. The same entrypoint
creates the isolated stack, prepares the course, measures, verifies source
stability and removes its owned containers/volumes/networks.

```bash
# Example values for ONE S1 point, only after approval; not executed in P11-A.
c=1
rep=1
python3 scripts/dev/run_check.py --name "p11-s1-c${c}-r${rep}" \
  --output .data/p11-rental/checks --timeout 2400 -- \
  bash eval/perf-p0/run.sh --offline --profile rental --scenarios S1 \
  --concurrency "$c" --seconds 60 --timeout 60 --mock-delay-ms 150 \
  --run-deadline 1800 --output ".data/p11-rental/s1-c${c}-r${rep}"
```

For S3 change `--scenarios S3`; for default S2 change to `--scenarios S2
--requests 64 --qa-per-minute 10` **instead of** `--seconds 60`. For separately
approved S2 capacity testing use `--scenarios S2 --seconds 60 --qa-per-minute
100000`. Every point and repetition is a separate invocation. The outer timeout
exceeds the internal deadline by 600 seconds to allow cleanup; bootstrap failures
or timeouts are retained, not relabeled as performance observations.

## Observation, stops and cleanup

Start read-only observations before warmup, retaining UTC timestamps through
cleanup. On this disposable machine, use `vmstat 1`, `iostat -xz 1` and
`pidstat -dur 1`; keep their tool versions/interval/overhead identical in paired
trials. Capture Docker stats only for project names in this run's `result.json`
and Java/Agent processes in its recorded `children`. Record per-core utilization,
CPU steal/throttling, RSS/available memory, swap/OOM, disk I/O, filesystem free
space and PostgreSQL connections/query waits using read-only observations of
the **owned** instance. Never inspect other worktree databases or user data.
Include driver CPU/event-loop saturation: closed-loop rates may reflect the
client as well as the service. The framework does not automatically prove a
hardware bottleneck or attribute CPU time to embedding/SQL/lock hold time.

Stop a point if it exceeds the internal deadline, cleanup cannot drain a Tutor
turn, ownership/revision checks fail, evidence cannot be verified, memory/disk
approaches the operator's approved safety threshold, OOM occurs, or unexpected
external network/provider activity appears. A run with lost telemetry or a
changed fingerprint is ineligible for comparison. Expected busy 503/QA 429 is a
reported failure, not by itself evidence of hardware exhaustion. Do not retry,
add sleeps/backoff, raise workers, alter locks or relax budgets to improve numbers.

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
# For a point intended to prove direct busy rejection, also add --require-busy.
```

Export `result.json`, `requests.jsonl`, reports, redacted logs and telemetry with
a checksum manifest. Confirm no owned containers/volumes/networks or application
children remain before releasing the rental. Preserve failures and raw attempts.

## Interpretation and before/after comparisons

For each repetition report attempted/success/failed counts, error categories,
429/503/Retry-After, successful operations/s, attempted operations/s, all/success/
failure P50/P95 and timeouts. S3 additionally reports submit-to-terminal latency.
Show each repetition and spread; do not select only the best. Warmups, admission
window, operation timeout, polling, cleanup/drain time and clock resolution must
be reported. Do not pool per-run percentiles; recompute pooled percentiles from
eligible raw rows only when the conditions are identical.

Freeze hardware/SKU, image and dependency fingerprints, corpus/text/chunk hashes,
query, embedding, injected delay, owner/course topology, thread/worker counts,
limits, initial empty databases, warmup, stop conditions and telemetry overhead.
Record both source SHAs and the exact optimized diff. Future optimization is a
separate task: rerun the same matrix, account for error-rate changes, compare
successful P95/throughput, and report all failures. A lower all-attempt P95 caused
by more fast rejections is not an improvement. Schema-v1 latency included cancel
cleanup; never mix it with schema-v2 operation/turn latency.

Resume claims require approved independent-machine execution, clean source,
complete repeatable evidence and an honest workload/mode/hardware description.
A verified before/after claim additionally needs both measured baselines under
the same conditions. Mock/hash384 results may support only clearly qualified
mechanism/admission claims, never real-provider latency/quality, semantic
retrieval performance, teaching quality or general production capacity.
Historical SameScale `DEV_SMOKE_NOT_RESUME` (including 61/64 busy responses),
single tiny samples, policy-limited throughput and unexecuted plans are
development diagnosis only. No performance number is prefilled by this plan.
