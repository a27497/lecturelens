# Tutor scale preparation v2 verification

**Mock mechanics verified; real quality NOT_RUN.** This additive version closes the three audited gaps:
a frozen development execution queue, an exhaustive diagnostic checklist, and task/refusal/context scoring
with explicit scheduled denominators. No real generation, embedding, reviewer, account/credential inspection,
public-course expansion, CI change, deployment, push or PR occurred.

## Executable identity and scope

The executed code is **`190499cb53857bc4b860f52224d51859639e30a9`** on `codex/tutor-scale-preparation`,
starting from `74208e10b37583b951cf2a45a0b644bfed11b902` in the same initially clean independent workspace.
Candidate `tutor-scale-preparation-v2-r4` SHA-256 is
`f25a4f928b863caf20d5e2f241056a704a8184ce5b2d887fa788691701e77320`.
Queue SHA-256 is `b0ed6c1ee7c7ad774016fc3bb0214fe5ef18c808fca9919a9dfaba7e0a9c2c84`.
The final evidence commit changes only this report and `verification.json`; executable inputs remain pinned
at the tested bytes. [Machine-readable verification](verification.json) binds the key local artifacts by hash.

The queue is exactly `queue-03`, `queue-09`, `ecology-02`, `ecology-08`: **2 development courses, 4 complete
sessions, 20 learner turns**. Course membership, full task bytes, dataset lock/version, manifest hash and
scope counts are checked before output/ledger creation. No Energy holdout authority/session is created.
Preflight reads v1 manifests for identity verification; compatibility replay reads already-existing Mock data,
not a new holdout quality trial. The previous 320-turn data, holdout list and original 100/20 sample are intact.

The new driver reuses the old TutorRuntime/Store, SnapshotAuthority, TutorProvider, review_turn, RecordedChannel,
MetadataTransport, Ledger/TutorPolicy and reservation arithmetic. It adds scope orchestration outside the old
hardcoded four-course runner. No product runtime or old frozen file was edited. Real mode requires explicit
queue, CLI/environment opt-in, pricing and separately supplied call/USD caps; Mock defaults do not authorize
future spending. Model choices, live call cap, current prices/balance and live USD authorization remain unconfirmed.

## Actual checks

* **34 tests passed, zero failures/skips**: 23 v2 scope/diagnostic/annotation/denominator cases and 11 unchanged
  v1 tooling tests. Checks cover duplicate/unexpected data, complete and partial absence, live caps/queue
  rejection, immutable original selection, import/hash binding, explicit source of annotations and null rates.
* A separate negative-preflight program corrupted a new temporary queue copy and a separate temporary data
  copy. Both were refused (`QUEUE_HASH_MISMATCH` / `DATASET_CHANGED`) before any Ledger construction or output
  directory. The original dataset was not modified.
* Independent hand-constructed examples check full planned counts, assessed counts, missing/execution failures,
  justified versus unexpected abstention, no-citation coverage, context judgment changes with identical text,
  and binary agreement/kappa including degenerate/no-pair cases. These examples do not relabel real outputs.
* Ruff lint/format and Git whitespace checks pass. Completed guarded final test/Mock/negative-check records
  report zero denied network attempts. Default sends used only MockTransport and the isolated local PG.

All E2E cases below repeat the same **20-turn** frozen development queue. They are not 80 unique new tasks.
Each uses a fresh ignored output directory and single-use ledger/run name; no prior run was resumed.

| Scenario | Completed | Failed | Missing result | Attempted requests | PG/JSONL events | Diagnostic items | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| normal | 20 | 0 | 0 | 60 | 120 | 0 | 0 |
| first Mock timeout per course | 18 | 2 | 0 | 56 | 112 | 2 | 1 |
| first malformed Mock response per course | 18 | 2 | 0 | 56 | 112 | 2 | 1 |
| two-request total reservation cap | 0 | 2 | 18 | 4 | 4 | 20 | 1 |

Budget-stop has two successful search calls/reservations and two later pre-reservation refusals. All four
attempts are recorded; only two reservations have terminal events. A charged failed settlement is never a
successful answer. Failure/checklist counts are not mixed into a random estimate. An additional explicit
**hand-constructed pre-first-request crash fixture** has no results at all: diagnostics still find 20 MISSING
turns, zero observed attempts, and no semantic score.

The independent verifier checked all expected keys and development ownership, exact PG event JSON contents
and ordering, selected published turn fields, raw/aggregate mirrors (including citations), actual owner
811008 and matching session scopes. Across the four final
cases all **348** persisted event objects match their JSONL objects. This proves the two accounting mirrors
match, not that cited claims are semantically true or that a real provider sent/charged anything.

Every normal/fault case also completed export -> empty A/B import -> score. Pilot A has 20 census assignments;
B has five predeclared overlap assignments. Inventory/task annotations remain zero, semantic rates are null,
real human/model agreement is NOT_RUN, and no fake review becomes a real model/human pair. The diagnostic
output also catches failed calls after an otherwise completed turn (tested with a separate constructed case).

## Denominator evidence

The normal queue always reports 20 expected/executed/completed/scorable turns, zero failed/missing and zero
assessed task judgments. Task correctness has 20 applicable turns, expected abstention 8, contextual follow-ups
8, and expected-answer coverage 12. Missing annotations stay visible. Actual abstentions on expected answers
and uncited expected answers are mechanical counters, not inferred semantic judgments.

The independent arithmetic fixture has 20 scheduled / 18 completed / 1 failed / 1 missing / 4 task-assessed,
with two constructed correct labels. Assessed task rate is 2/4; confirmed positives over the full planned
queue is 2/20. Supported expected-answer coverage is 1/12 despite the selected cited pair accuracy being 1.0.
Refusal and context judgments each have a constructed 1/2 assessed rate. These are **HAND_CONSTRUCTED_FIXTURE**
values only: they verify that selective answering/citing cannot silently remove scheduled coverage units.
No actual Tutor quality, human consistency or learning score is inferred from them.

The old original random protocol remains exactly 100 primary / 20 overlap. A fresh export from the old full
Mock run produced byte-identical `packet-A/B.json` and empty `annotation-A/B.json`. It was not replaced by
our separate pilot census or exhaustive failure review. The old 75/25 development/holdout assignment remains.

## Isolation, preservation and retained failures

Before restoring PG we checked compose project/config labels, loopback 25841/free port, exact image digest,
volume ownership/unique consumer, and 0.5 CPU/384 MiB limits. Only the existing synthetic isolated container
was started. Original v1 PG run/event tables and non-v2 sessions/turns were hashed before and after final
workflow; their row contents are unchanged. The **296** protected old source/output/check files also match
before/after SHA-256. Product code, legacy eval directories and CI have no diff from `74208e1`.

Initial import/collection failures, the original ambiguous verifier import, and the owned R3 workflow
cancellation remain in `.data/dev-checks/` and `.data/tutor-scale-v2/`; no failure was reclassified as success.
The shared exports were made explicit and the new verifier renamed `verify_pilot.py` to avoid collision during
combined test collection. Its regression test passes in the final 34-case run. Initial candidate snapshots,
source archive and commits are retained, and final R4 cases have fresh names/identities. Cancellation matched
the supervisor PID/start ticks, then awaited CANCELLED with complete cleanup; no broad process matching.

The final supervisor is SUCCEEDED with complete cleanup. The isolated PG container is again **stopped**, its
volume retained. No other container/workspace was changed. Resources remained about 13 GiB available RAM and
44 GiB free disk. All raw transcripts, ledgers, packet identity keys and check logs stay ignored.

## Local evidence

| Evidence | Workspace-relative path |
| --- | --- |
| final scope, config, raw turns, calls and ledgers | `.data/tutor-scale-v2/scalev2-normal-r4/` |
| timeout/malformed/budget raw cases | `.data/tutor-scale-v2/scalev2-{timeout,malformed,budget}-r4/` |
| all-results-missing fixture and checklist | `.data/tutor-scale-v2/fully-missing-r4-fixture/`, `diagnostic-fully-missing-r4.json` |
| separate failure checklists | `.data/tutor-scale-v2/diagnostic-{normal,timeout,malformed,budget}-r4.json` |
| pilot census packets and empty imports/scores | `.data/tutor-scale-v2/review-*-r4/`, `import-*-r4.json`, `scores-*-r4.json` |
| independent complete workflow/PG reconciliation | `.data/tutor-scale-v2/workflow-r4-verification.json` |
| negative preflight / hand arithmetic | `.data/tutor-scale-v2/preflight-negative-r4.json`, `independent-arithmetic-r4.json` |
| final test XML / owned terminal logs | `.data/tutor-scale-v2/final-r4-tests.xml`, `.data/dev-checks/scale-v2-*/` |

Current limits remain: short synthetic English microcourses, fixed five-turn shape, no long/Socratic or
natural-course generalization evidence, no actual independent annotators, no current model/price/balance
verification and no real generation/reviewer. Segmentation and semantic annotations still require an external
human procedure. Future real models, call cap and USD budget require separate confirmation. This task stops
at local commits. **Real quality, human agreement, real tokens/cost and learning effects are NOT_RUN.**
