# Tutor frozen pilot and task review v2

Additive evaluation tooling, **Mock preparation only**. This directory fixes pilot scope, diagnostic completeness
and task-score denominators. It imports the immutable v1 runner's runtime, authority, provider, reviewer,
transport recording and PG/JSONL budget ledger. No product runtime, old dataset, candidate, result or random
blind sample changes. The previous 320-turn suite and [v1 protocol](../tutor-scale/README.md) retain their identity.
[This version's verification record](REPORT.md) separates execution evidence from quality.

## Frozen development execution queue

`development-queue-v1.json` selects exactly two complete sessions from each of two development microcourses:
`queue-03`, `queue-09`, `ecology-02`, `ecology-08` — **2 courses / 4 sessions / 20 learner turns**. It inherits
`dataset_version=tutor-scale-synthetic-v2`, CC0 original synthetic materials and their evidence locators. Each
session has five complete scripted turns. Its task bytes, course ownership, split, dataset lock and total scope
are verified before output/ledger creation. `queue-lock.json` freezes the queue bytes; `candidate.json` freezes
all executable/protocol inputs and the queue. Changed queue, task, dataset hash or version fails closed.
There is no arbitrary session filter, no automatic full-suite fallback and no selection through budget exhaustion.

The v1 preflight still reads its old data manifests to verify immutable inputs. The actual execution authority
contains only the two selected development courses; no Energy holdout session is created or searched.
The queue is intended to check contextual arithmetic, cancellation constraints, endpoint counting and calibration
conditions. Its fixed five-turn shape and very short synthetic evidence do not establish natural-course quality.

Every output directory/run name is single-use. `expected-turns.json` is written **before the first request**,
followed by config recording scope, source version/hash, candidate, code SHA and persistent caps. `turns.jsonl`
accounts for all 20 scheduled turns, including explicit MISSING rows after a stopped shard. If a process dies
before aggregate creation, diagnostics use available per-course raw records and the frozen queue. No resume,
replay, refund or automatic budget transfer is introduced.

## Mock execution on this server

The existing isolated project must first be verified: compose label/config path, image digest, loopback 25841,
volume ownership and unique consumer, free port, available resources and synthetic role. Do not infer safety
from a DSN alone. It uses 0.5 CPU / 384 MiB and owner 811008, separate from v1 run records. No browser acceptance
account, Java/MySQL, media, production or student data is used. Only start/stop this container; retain its volume.

```bash
# Only after verifying the existing stopped container and its volume/port.
docker start lecturelens-tutor-scale-prep-20261107-postgres-1
# From repository root; use NEW names on each invocation.
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py \
  .data/tutor-scale-v2/network-pilot-NEW eval/tutor-scale-v2/pilot.py \
  --queue eval/tutor-scale-v2/development-queue-v1.json \
  --output .data/tutor-scale-v2/pilot-NEW
```

The unchanged safe launcher strips provider/proxy/tracing environment and installs a socket fence permitting
only the isolated PG and test loopback. Default Mock never reads a provider key and uses MockTransport.
Use the existing bounded supervisor from `.data/dev-tools/scripts/dev/run_check.py` for long checks:
`--name UNIQUE --cwd "$PWD" --output-root .data/dev-checks --timeout 300 -- COMMAND`. It is the committed
`b82bebf` supervisor already documented by v1. Cancel only this owned supervisor after PID/start-tick validation
and await its terminal record. No global process cleanup or manipulation of another workspace.

Mock defaults allocate **160 total calls**, equally partitioned into two 80-call persistent shards. The Mock
USD default is 1.40 total (0.70 each), inherited reservation arithmetic, **not current prices or spending
approval**. Per-shard ledger caps, reserve-before-send, unknown-call blocking, per-turn runtime limits and
bounded reviewer retries are unchanged. Odd call limits round down per shard and cannot exceed the total.
`--max-calls 2` tests early budget stop; `--fault timeout` or `--fault malformed` injects a first fake request
failure in each course. Each incomplete run exits 1 and keeps all scheduled/missing outcomes.

A future real pilot must use this same frozen queue with explicit `--live`, environment opt-in, compatible
pricing artifact **and explicitly supplied `--max-calls` and `--max-usd`**. Missing any gate fails before send.
No Mock budget default becomes live authorization. No synthetic fault is permitted in live mode. The existing
hardcoded model aliases/route and historical rate ceilings are inherited, not currently verified or selected
for a paid trial. An operator must independently confirm model availability/identity, tool/usage compatibility,
current price coverage, actual balance and authorized caps. No provider account or credential is inspected by
this task. Current prices and future authorized USD budget remain UNKNOWN. This document does not authorize
real execution. Mock tokens and legacy ledger amounts never become real usage/billing metrics.

## Failure review is a diagnostic census

```bash
agent-service/.venv/bin/python eval/tutor-scale-v2/diagnose.py \
  --queue eval/tutor-scale-v2/development-queue-v1.json \
  --run .data/tutor-scale-v2/pilot-NEW --output .data/tutor-scale-v2/diagnostic-NEW.json
```

This checklist is independent of v1's unchanged random **100/20** sample and its population/statistics. It
contains every failed/cancelled, timeout/deadline, malformed/protocol, failed/retried call, failed review and
missing scheduled result. Missing results are derived from the frozen expected queue, not only observed rows;
when every result file is absent there are still 20 MISSING items. If bound run metadata is absent, output
explicitly says UNKNOWN/incomplete metadata: the expected list is known, actual execution is not certified.

Each diagnostic item has turn/session/request trace where available, reason codes, failed call indices, prior
conversation, learner text and reference. Duplicate or unexpected keys, changed plan/task scope, inconsistent
raw/aggregate mirrors or version mismatches are rejected, never silently de-duplicated. A process-crash orphan
call makes a turn attempted even if its result is missing. Config-declared Mock fault types are labeled
`MOCK_INJECTED_*`; generic real request errors are not falsely relabeled as proven timeouts or malformed bodies.
A failed call followed by a completed answer still enters this diagnostic list.

This checklist is **not a random sample**. Do not pool it with the primary sample to estimate population
quality, replace failed sampled units or claim a larger independent sample. It is a separate exhaustive failure
analysis. The 20-turn pilot can itself be reviewed as a census; it does not masquerade as the 320-turn random
sample. All exports refuse overwriting existing files.

## Independent annotations and pilot census

```bash
agent-service/.venv/bin/python eval/tutor-scale-v2/review.py export \
  --queue eval/tutor-scale-v2/development-queue-v1.json \
  --run .data/tutor-scale-v2/pilot-NEW --output .data/tutor-scale-v2/review-NEW
agent-service/.venv/bin/python eval/tutor-scale-v2/review.py import \
  --key .data/tutor-scale-v2/review-NEW/private-key.json \
  --packet .data/tutor-scale-v2/review-NEW/packet-A.json \
  --ratings .data/tutor-scale-v2/review-NEW/annotation-A.json \
  --output .data/tutor-scale-v2/import-A-NEW.json
# Independently repeat import for B, then:
agent-service/.venv/bin/python eval/tutor-scale-v2/review.py score \
  --queue eval/tutor-scale-v2/development-queue-v1.json \
  --key .data/tutor-scale-v2/review-NEW/private-key.json \
  --imports .data/tutor-scale-v2/import-A-NEW.json .data/tutor-scale-v2/import-B-NEW.json \
  --output .data/tutor-scale-v2/scores-NEW.json
```

A receives the **20-turn pilot census**; B independently receives the five predeclared overlap turns in the
queue (one per category). Both display orders are independently seeded. Identity/model/version/review labels
stay out of packets; key mapping is 0600. Text is preserved, so self-identifying answer text may compromise
blinding and must be recorded. Only give each rater their own packet/template. Files do not prove that people
actually annotated independently. Save their original submissions before any adjudication.

Templates contain no judgments. `annotation_source` starts UNANNOTATED. Actual manual work must state HUMAN;
synthetic arithmetic tests state HAND_CONSTRUCTED_FIXTURE and cannot become real human results. `complete:true`
attests to the full assertion inventory, reason, source support and any supplied task judgments. Use exact
answer/evaluation spans in `claims` and all claim–citation pairs in `citation_checks`; supported pairs require
exact attached evidence quotes, reusing v1 validation. Missing/uncertain labels never become successes.
All assigned units must remain in the file. A noncompleted execution cannot receive semantic scoring; diagnose
its failure separately. A partial semantic judgment must not hide under `complete:false`.

Manual fields (boolean or null, never inferred from strings):

* `task_correct`: responsive and course-grounded, correct conditions/arithmetic/false-premise correction,
  appropriate answer versus clean refusal, with appropriate citations and conversation grounding.
* `abstention_correct`: on an expected-abstain turn or an actual refusal, judge whether the refusal/absence
  of substantive answer is justified and clean. A substantive outside-course answer is false; an unjustified
  refusal on an expected-answer turn is false. A completed clean refusal can be true even without citations.
* `context_consistent`: on scripted contextual follow-ups, judge prior referents, learner constraints, source
  conditions and cross-turn evidence. Account for failures/unpublished prior answers; do not invent an
  antecedent. Clarification may be context-consistent yet fail the requested task. Text equality is irrelevant.
* `overall_supported`: the unchanged supported/unsupported/uncertain whole-answer judgment for binary support
  agreement, distinct from task correctness. `null` task fields mean not assessed, not false.

Input packet, key, queue and source artifact hashes are bound/rechecked at import/score; changed run records,
missing assigned units and repeated raters are refused. The scorer revalidates imported ratings instead of
trusting a hand-edited import. Actual authorship and semantic segmentation still require human procedure.

## Units, denominators and missingness

Execution counts are always the full **20-turn expected queue**: executed results = completed + failed/cancelled;
missing results = expected minus executed results. `attempted_turns` additionally includes orphan call evidence
before a crash. `scorable_turns` is completed published results, not a success judgment. Report these alongside
inventory-annotated and task-assessed counts; no successful-only headline is provided.

Every semantic measure exposes applicable planned, scorable completed, assessed, missing annotation and
execution-unscorable counts, positives/negatives, assessed rate and confirmed positives over all applicable
planned turns. The last is a **conservative confirmed lower bound**, not an imputed human failure rate or an
unbiased quality estimate. Failed/missing executions contribute no confirmed positive but stay in that planned
denominator. Until there is at least one valid judgment, rates and positives/negatives are null and status
NOT_RUN. No model task label or human label is synthesized from a completed run or a fixed Mock review.

* Task correctness: all 20 planned turns. Expected-abstention correctness: the 8 expected-abstain turns.
  Combined refusal correctness: those 8 plus any actual refusal on an expected-answer turn; unjustified
  abstention cannot remove a turn from the task or expected-answer coverage denominators.
* Cross-turn consistency: all 8 scripted contextual follow-ups, even following failed prior turns. Current
  execution failure/missing stays execution-unscorable. Only explicit manual labels determine semantic rates.
* Citation support accuracy: supported / all annotated claim–citation pairs; uncertain/unsupported count
  zero supported. Citation presence and supported coverage: cited/supported citation-requiring assertions /
  all annotated citation-requiring assertions. These are annotated-subset metrics and always appear together.
* Expected-answer turn coverage: **12 planned turns**, including wrong abstentions, uncited answers, failures
  and missing. A human-verified inventory contributes presence only when the answer has substantive claims
  and all required claims have citations; supported coverage additionally requires support for every required
  claim. An expected-abstain turn is outside this denominator, so a justified clean refusal is not penalized.
  An unexpected refusal contributes no coverage even though it has zero claim–citation pairs.
* Outcome counts separately show actual abstentions on expected answers, uncited expected answers and
  expected abstentions. These are mechanical counts, not semantic correct/incorrect labels.
* Model/human support agreement and binary Cohen's kappa require valid labels from a completed **real**
  reviewer and actual HUMAN primary annotations. Failed reviews, uncertain, missing and fake reviews are
  excluded with eligible/comparable/excluded counts, never counted as agreement. Human/human overlap also
  requires two HUMAN sources; other sources keep real agreement NOT_RUN. Zero paired samples returns null;
  degenerate marginals keep kappa null with a reason. No passing threshold is asserted.

All current output quality/cost and real token metrics remain NOT_RUN; hand-constructed labeled examples
are explicitly MOCK_NOT_QUALITY. Pair accuracy alone never establishes task quality. No real labels are
available in this task. Current synthetic scope, fixed dialogue order and lack of long/Socratic conversations
remain limitations. Original 100/20 sampling, its scoring protocol and all old outputs are untouched.

## Checks and boundaries

```bash
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py \
  .data/tutor-scale-v2/network-tests-NEW agent-service/.venv/bin/pytest \
  -q -p no:cacheprovider eval/tutor-scale-v2/test_v2.py
# Read-only DB/content verification; source scope is still validated first.
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py \
  .data/tutor-scale-v2/network-verify-NEW eval/tutor-scale-v2/verify_pilot.py \
  --queue eval/tutor-scale-v2/development-queue-v1.json \
  --run .data/tutor-scale-v2/pilot-NEW --database --output .data/tutor-scale-v2/verify-NEW.json
```

Tests target frozen scope/hash rejection, fully/partly absent results, failures after retries, original sample
invariance, annotation binding, full planned denominators, hand-constructed arithmetic and no-label NOT_RUN.
Mock E2E validation separately checks the normal queue and bounded timeout/malformed/budget-stop cases in the
isolated PG. It does not establish actual model intelligence, real reviewer validity, human independence,
current pricing, billing, learning effects or real-course generalization. No CI, deployment or paid run changes.
