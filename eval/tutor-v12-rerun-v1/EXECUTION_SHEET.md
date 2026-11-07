# Unapproved v12 full-development real rerun

**NOT AUTHORIZED / NOT_RUN.** This freezes a future single-run procedure, not
spending permission. The old USD 10 grant and any unused calls/money have expired.
No real model, embedding, reviewer, account query or paid probe is part of entry
preflight. Wait for a new explicit batch amount/request authorization.

| Item | Frozen value / required confirmation |
| --- | --- |
| Agent | `p8-tutor-repair-context-v12-development`; manifest `4540369887eb2d84f79ee5351a8e1c0c82af859be8ff8d364ce7faf262a3afb2` |
| Scope | All original 16 consumed development positions / four new sessions / two courses; 12 answerable, four insufficient; no SQL |
| Run plan | `run-plan.json`, SHA-256 `6a684a138d9fe2a04ccbb51f9d3bdbab25b44b5465a21a0c1082bbbc33dad825` |
| Original batch | `4efdabb65a323155366184523757779a04b7ddfc7baf6717638590bdb91100ad`; original grading/source/data locks unchanged |
| Adapter/protocol | `adapter-lock.json` pins entry/verifier/plan/protocol/tests; version `v12-session-isolated-live-v1`; exact adapter hash in verification report |
| API/model | `deepseek-flash`, only `https://api.deepseek.com/chat/completions`; moving alias, immutable backend version UNKNOWN |
| Model settings | Temperature 0, thinking disabled, maximum output 1,200 tokens/request |
| Reviewer/concurrency | Off / 1; no reviewer or embedding sends |
| Retries/repairs | SDK/transport/application transport retries 0, redirects disabled; existing one format and one mode repair only |
| Total requests | **New integer authorization required, 1–80 total**, including failed/repair sends; lower caps can leave scheduled positions missing |
| Total local envelope | **New USD amount required, >0 and ≤0.70**; ceiling is not authority or expected spend |
| Ledger allocation | One new global persistent PG/JSONL ledger; old A/B allocations, ledgers and allowance are not reused |
| Price/access/balance | **UNKNOWN / not refreshed or queried in this task**; execution-date reviewed compatible price observation required |
| Actual supplier bill protection | **UNKNOWN / not guaranteed** by local enforcement; separately acknowledge this limitation |

## Free preparation

From the requested worktree, this command validates all frozen inputs and returns
configuration only. It neither needs nor starts the database:

```bash
PYTHONPATH=agent-service/src agent-service/.venv/bin/python \
  eval/tutor-v12-rerun-v1/rerun.py \
  --agent p8-tutor-repair-context-v12-development --model deepseek-flash
```

For bounded Mock checks, use `eval/tutor-scale/safe_exec.py` and the stopped dedicated
PG on loopback 25841 after verifying its compose path, pinned image, sole volume
consumer, limits and free port. The socket launcher strips provider/proxy env and
rejects the live branch even when its opt-in is supplied. Use the existing
`scripts/dev/run_check.py` supervisor, a unique output/name and new synthetic
namespaces. Stop only that dedicated DB afterward, retaining its volume/evidence.
No Java/MySQL/browser stack or new server is needed.

## Request and money bounds

Normal path: **16 × (search + finish) = 32 requests**. With a second search on every
turn: **48**. With both existing one-shot repairs after two searches/finish:
**16 × 5 = 80 theoretical maximum**. Runtime deadline, call and serialized-context
bounds may stop earlier; neither completion nor this exact pattern is guaranteed.
Local tools/search make no external embedding/search calls. Ignored parallel tool
proposals do not create extra provider requests. Reservations, rejected-before-send
channel attempts and actual transport dispatch attempts are recorded separately.

The inherited local ledger reserves **wire UTF-8 bytes × 300 nano-USD + maximum
output tokens × 1,200 nano-USD**, then settles successful known usage at the same
frozen peak/no-cache basis (USD 0.30 input-miss / USD 1.20 output per million).
These are **historical frozen accounting constants**, not newly verified prices.
Failures/unknown outcomes retain the reservation; divergent/pending/blocked
accounting stops dispatch. Usage/cache details and public rate-based estimates
must be reconciled after the run; actual account debit stays UNKNOWN without
billing evidence. The byte proxy is not a proven bound on all supplier framing or
hidden charges, and post-response checks cannot undo an incurred request. Thus
**the local envelope is not a hard supplier invoice cap**.

Before any real request, reopen and retain the actual-date official pricing source
and numeric rates, with a source hash. The inherited checker requires a USD /
1,000,000-token observation for `deepseek-flash` dated that UTC execution day with
compatible peak input-miss `0.30` / output `1.20`. If stale/incompatible, stop; do
not modify the frozen rates or bypass the check. Account balance, credits, actual
invoice protection and model availability remain unverified here. No paid
availability probe is authorized by this sheet.

## Future live template — intentionally non-runnable placeholders

Only after a new grant confirms this model/alias limitation, the exact 16-position
scope, numeric total requests, numeric USD cap and billing limitation, reverify the
isolated DB and instantiate every placeholder. Provision the existing evaluation
credential only into the sender's environment; never inspect/output it or put it
in argv/logs. The flags below are technical acknowledgments, not permission by
themselves. No scheduling/automatic execution is configured.

```bash
LECTURELENS_REAL_EVAL=1 PYTHONPATH=agent-service/src \
  agent-service/.venv/bin/python eval/tutor-v12-rerun-v1/rerun.py --live \
  --agent p8-tutor-repair-context-v12-development --model deepseek-flash \
  --reviewer off --concurrency 1 \
  --max-calls '<NEW_USER_CONFIRMED_INTEGER_AT_MOST_80>' \
  --max-usd '<NEW_USER_CONFIRMED_USD_GT_0_AT_MOST_0.70>' \
  --pricing '<EXECUTION_DATE_REVIEWED_COMPATIBLE_PRICE_OBSERVATION_JSON>' \
  --ack-new-batch-authorization --ack-ledger-not-billing-cap \
  --output '.data/tutor-v12-rerun-v1/<GLOBALLY_UNIQUE_NEW_BATCH_NAME>'
```

Run that sender through `scripts/dev/run_check.py` with a unique terminal record;
there is no transport retry or automatic continuation after a supervisor failure.
Never run live through the Mock socket launcher. Apply [the frozen failure
protocol](PROTOCOL.md): local failures preserve/close their session, global or
unknown safety/accounting failures stop all, and every skip/missing position
remains in the 16-position census. Do not reset a ledger to resend an unknown call.

Perform one whole new run, then review all scheduled outcomes against original
source/rubric. Report both batch and conditional completed-answer correctness,
completed/failed/skipped/missing counts and full citation inventories/denominators.
Keep all errors and uncertainties; no quality-driven rerun. This is a development
regression with candidate and stop-policy changes, not an isolated quality-effect
estimate or independent holdout. Do not reuse old successful answers as new results.

After reconciliation/source review, stop the dedicated DB and retain evidence.
The authorization ends with this single batch; no repairs to the candidate,
follow-on batch, SQL holdout, expansion or learning-effect trial is authorized.
