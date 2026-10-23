# Offline Study expense evaluation

The opt-in experiment reuses the existing acceptance expense ledger against main
e34d8c596d74d4320ce6a224359190374520e4d3. It exercises the real Study runtime,
ChatProvider parser, journal and PostgreSQL with deterministic synthetic responses.
It does not change ordinary workers, user routing, Java QA, migrations or budgets.

There is no official HTTP sender, credential loader or live/serve command. A live
policy is rejected, including one with a nonempty authorization identifier. Tests
use `model_mode=real` to exercise the existing parser/routing path; all responses
are Fake and do not certify any actual Provider, teaching quality or billing.

## Entry and isolation

From an independent checkout with locked dependencies installed:

```bash
agent-service/.venv/bin/python scripts/eval/acceptance-cost-egress.py plan

# AGENT_TEST_DATABASE_URL must explicitly target a separate loopback test PG,
# named lecturelens_agent_test, on a port in 20000..32767.
agent-service/.venv/bin/python scripts/eval/check-study-offline.py \
  --database-port YOUR_TEST_PORT --network-records /private/new-network-records \
  -- tests/test_acceptance_cost.py -q
```

Use the local check supervisor when available and unique output paths; do not
overwrite previous trials. The guarded runner strips inherited credentials and
proxy settings, pins libpq hostaddr, disables user site imports and installs a
Python DNS/socket audit fence before pytest, including spawned Python children.
Only the specified test PG and ephemeral loopback servers are allowed. This is
not an OS sandbox; native library traffic is not covered by Python socket counts.
Never supply a production DSN, service config, key or account to this entry.

The 56 pre-existing application modules are verified against an immutable SHA256
manifest. Any change requires a separately reviewed new candidate. Expense code,
runner and fixture identity also belongs to the enclosing commit/artifact digest.
The ordinary application's initialization never installs the expense tables;
only explicit isolated tests create them. Per-test schemas and synthetic owners
prevent history or reservations from being shared with other trials.

CI already supplies a real test PG on 5432. A test-only loopback forwarder exposes
that explicitly selected test DB on a free ledger-compatible port; the ledger's
address validation remains unchanged. Neither application nor workflow is changed.

## Preserved boundaries

| Boundary | Offline experiment |
| --- | --- |
| Main runtime | 6 model calls, 8 logical tools, 64,000 conservative input/output reservation, 90-second Run deadline, at most two candidates |
| Feedback request | Same Run limits; existing per-request timeout at most 20 seconds |
| Output | Decision 900, practice review 300/900/1200 according to main's review stage, feedback 900 |
| Input | Entire outgoing UTF-8 JSON at most 65,536 bytes, text and client function tools only |
| Expense policy | One Session, one practice Run and its precise saved-attempt feedback Run, at most 6 calls each / 12 total |
| Simulated money | At most 20,000,000 micro-CNY reserved; whole-context input allowance makes at most 9 admissions possible |
| Failure | No refund; pending/unknown outcomes block subsequent sends; retry/quality-rejection events prevent further simulated paid repair |

Main reserves input using its existing JSON byte estimator. The ledger validates
the journal request fingerprint and uses main's review-stage output allowance;
it does not reintroduce the old candidate's compact estimator, context compression
or method-observation optimization. Scoped statuses use main's public-status
normalization; frozen learning scope and attempt inheritance remain authoritative.

`reserved` and `sent` describe local reservation/dispatch, not supplier receipt or
charging. `observed` means usable reported usage, not protocol/quality acceptance
or a reconciled bill. Missing usage is not zero; partial statistics are retained
as observations, and `provider_billed_micro_cny` remains NULL.
The historical 2/8 CNY-per-million simulation assumptions are not a supplier price
lock or account limit. A 20 CNY envelope cannot complete the full quality cohort.

Crash recovery does not resend an unresolved operation or replenish reservations.
An observed response committed only in the expense ledger does not substitute for
the runtime's committed journal. Cancellation before dispatch rejects sending;
cancellation after dispatch cannot prove a remote computation or charge stopped.
The offline tests make no remote request to validate that distinction.

## Fourteen-module compatibility audit

Comparison: old frozen Agent 7b60d94dc0a221217e595dfb5fe5205ba474d03a to main.
The expense branch HEAD is 7b3e1f2f4c665b4878b73beb9fb65ab68558a1d4; its historical
verified artifact is c7c5d3ddc1f0c4137c642f6b6ef20c7811a302d8. Those historical
54/847 test results are not this candidate's results.

| Existing module | Difference and treatment |
| --- | --- |
| course_mcp/client.py | Scoped payload, route-specific signature and response fence. Keep main unchanged; expense adapter does not select Evidence. |
| course_mcp/contracts.py | LearningScope and explicit course expansion contract. Keep main unchanged. |
| study/approval.py | Scoped queued/running/waiting state normalization and resume. Keep main unchanged; adapter understands normalized active state. |
| study/authority.py | Dedicated scoped route and signature plus scope response checks. Keep main unchanged. |
| study/call_journal.py | Main budget rejection lacks the old diagnostic helper; journal identity/replay remains. Read main's existing fingerprint/purpose/stage; do not modify it. |
| study/context.py | Old compact preview/history optimizations are absent in main. Do not import them or change prompt/context. |
| study/contracts.py | Frozen scope input and explicit expansion. Keep main unchanged. |
| study/feedback_store.py | Feedback inherits its parent's frozen scope and scoped execution state. Keep main unchanged. |
| study/method_scope.py | Old source-hash observation reuse helper is absent. Do not import its optimization. |
| study/models.py | PR3 freezes version-specific single-turn evidence. Keep main unchanged; isolated placeholder snapshots make no certification claim. |
| study/provider.py | Main lacks old DeepSeek flag helper and compact reservation function. Validate fixed routes and add the synthetic non-thinking wire flag inside the evaluation adapter only. |
| study/resilience.py | Scope injection/checks around reads and recovery. Keep main unchanged. |
| study/runtime.py | Main uses its existing estimator and method-observation behavior, plus PR2 scope prompt. Adapt journal reading, not runtime execution. |
| study/store.py | Scoped persisted states, active-run fences and PR3 model evidence, different budget diagnostics. Keep main unchanged; normalize state only in expense admission. |

Main also adds learning_scope.py and model_evidence.py, bringing the frozen
application-module count from 54 to 56. No changes from PR35/36 are integrated.
Frontend/workspace differences are outside this adapter and need no modification.

## Remaining admission conditions and rollback

PR5-B remains **BLOCKED**. Dedicated account credentials, enforceable account-wide
spending cap, OS egress/DB-role isolation, a current-main live-capable candidate,
fresh frozen holdout data and explicit execution authorization are not supplied.
Do not run legacy evaluators that copy source-user credentials, restore the old
live sender, reset the ledger, create extra envelopes or use unlimited call mode.

Rollback removes/disables only this opt-in entry. Ordinary services and workers
do not need a deployment or database rollback. Keep any isolated trial ledger,
Run/attempt/checkpoint and failure evidence; never drop production fields or run
Flyway repair. PR1/PR2/PR3/PR4 and production release prerequisites remain intact.
