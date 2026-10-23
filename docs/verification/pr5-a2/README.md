# PR5-A2 offline expense adapter verification

Baseline: e34d8c596d74d4320ce6a224359190374520e4d3. Scope and fourteen-module
compatibility decisions: [offline evaluation contract](../../OFFLINE_COST_EVALUATION.md).

The new files align the existing expense ledger with current-main journal and
scoped states. All 56 pre-existing application Python modules match the frozen
manifest. No ordinary worker/Provider implementation, frontend, Java, dependency,
workflow or production migration is modified. No PR35/36 integration is included.

## Local result

Final local regression: **831 passed, 0 failed, 0 skipped**, including the new
72-case expense suite; 235.15 seconds. Ruff check and format passed. The existing
Starlette/AnyIO warning remains. The supervisor finished SUCCEEDED with complete
cleanup. See [machine-readable summary](verification.json). CI must be read for
the published HEAD separately.

## Verification scope

- Full Python regression uses a separate PostgreSQL 17.11 / pgvector 0.8.6 test DB,
  including the new 72-case expense suite; database tests must not be skipped.
- The new suite exercises exact budget boundaries, decision/review/feedback, strict
  scoped and legacy Runs, saved-attempt feedback, journal/expense identity matching,
  independent owner/Run rejection, 16 contenders, cancellation, and three real
  SIGKILL recovery points.
- Fake HTTP 429/500, malformed JSON, missing/invalid usage, exceptions, connection
  errors, a real stalled loopback socket, and runtime protocol repair verify that
  failures/unknowns cannot cause another sender invocation or refund.
- Environment stripping and external-DNS rejection run in spawned guarded Python
  processes. CI's test-PG port forwarding is verified independently, including
  retaining each forwarder's connector when another test replaces the global one.
- Healthy cases persist explanation/two questions, an exact attempt and feedback,
  then read them after Store restart. Per-Run expense rows equal its model-call
  journal count, with unique operation keys and both roles. Completed observations
  replay without another Fake request; outcome-unknown observations stop.

Authority/media behavior in this new suite uses explicit synthetic fixtures;
there is no new Java/browser/media end-to-end acceptance. Responses are Fake even
when the existing runtime uses `model_mode=real` to exercise ChatProvider. Mock
usage and monetary reservations are not bills or teaching-quality scores.

## Reproduction

Use an independent checkout/test PG. Supply only its DSN, and use a new supervisor
name, output root and network-record directory for every run:

```bash
# Use the installed local run_check.py supervisor when available.
agent-service/.venv/bin/python scripts/eval/check-study-offline.py \
  --database-port YOUR_TEST_PORT --network-records /private/unique-network-records \
  -- -q
agent-service/.venv/bin/ruff check agent-service/src agent-service/tests
agent-service/.venv/bin/ruff format --check agent-service/src agent-service/tests
```

Historical failures are retained separately: the first carried-over plan test
still expected 54 modules instead of main's 56. A later explicit two-hop forwarding
test was correctly rejected by the unchanged socket fence; the in-progress check
was cancelled by verified supervisor identity, and its focused failure preserved.
The correction tests connector ownership directly while retaining the original
test-DB-only network rule. Run limits, quality gates, permission checks and the
network allowlist were not relaxed. The new single-search/short-evidence fixture
does not inherit the old optimized double-search fixture's exact token totals.

## Limits and rollback

The original 6 model / 8 tool / 64k / 90s / two-candidate Run limits and one
Session/practice/feedback envelope remain. The simulated 20 CNY reservation admits
at most 9 requests and does not support the full quality cohort. Account cap,
current prices/bills, real Provider protocol and teaching quality remain unverified.
The aligned entry intentionally has no live sender or credential-reading command.

Disable/remove only this opt-in entry to roll back; ordinary workers are unchanged.
Keep historical evidence and any real future ledger; never reset money state or
run production DDL/repair. Production V25/final R, rollback bundle, keys/snapshots,
scope/checkpoint, worker isolation and release-order constraints remain in force.

PR5-B = BLOCKED. Real Provider requests = 0. No merge or deployment authorization.
