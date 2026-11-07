# First-real follow-up: development candidate v11

The original v10-r2 run, dataset, labels, manifests and product defaults remain unchanged.
This additive candidate addresses fragmented evaluation source context and decoded-response telemetry.
Its generic prompt guidance is experimental; no post-fix real response has been obtained.
See [REPORT.md](REPORT.md) for evidence, unresolved issues and verification results.

## Identity and scope

Explicit Agent `p8-tutor-grounded-v11-development` selects
`lecturelens_real_eval.tutor.grounded_runtime:GroundedTutorRuntime` with `PassageAuthority`.
`candidate.json` hashes the implementation, adapter, tests and historical adapter lock; verification
chains the unchanged v10-r2/P8/P10 identities. `retest-plan.json` and `scope-lock.json` bind the **same
original eight learner turns**: Python `python-01` and spreadsheets `sheets-01`, four turns each, no SQL.
`execution_authorized=false` is deliberate. A manifest is identity/scope evidence, never paid authority.

Source passages join adjacent original blocks up to six blocks / 1,000 characters, breaking before
headings, source changes and non-monotonic locations. An existing oversize block remains indivisible;
the inherited request and reservation limits still apply. Original material/snapshot bytes do not change.
Derived IDs hash context version plus member IDs. Published evidence retains exact member IDs, source
line ranges, content hashes, URL and attribution; the read/search ownership and revision checks are inherited.
Search still returns at most eight passages, at most twice per turn. This is an evaluation lexical path,
not a product embedding or ingestion change. Larger contexts can increase tokens and exhaust unchanged
budgets; there is no silent cap increase. Rank displacement remains possible.

## No-cost verification

From repository root, the preparation command needs neither DB nor credentials:

```bash
agent-service/.venv/bin/python eval/tutor-repair-v1/repair_run.py \
  --plan eval/tutor-repair-v1/retest-plan.json \
  --agent p8-tutor-grounded-v11-development --model deepseek-flash
```

After verifying the existing isolated container's project, image, loopback 25841, volume ownership,
dependencies, limits and available resources, start only that container. Use fresh output names:

```bash
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py \
  .data/tutor-repair-v1/network-NEW eval/tutor-repair-v1/repair_run.py \
  --mock --plan eval/tutor-repair-v1/retest-plan.json \
  --agent p8-tutor-grounded-v11-development --model deepseek-flash \
  --max-calls 40 --max-usd 0.70 --output .data/tutor-repair-v1/mock-NEW
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py \
  .data/tutor-repair-v1/replay-network-NEW eval/tutor-repair-v1/offline_audit.py \
  --output .data/tutor-repair-v1/replay-NEW
```

The amount above is **Mock reservation capacity**, not paid authorization or consumption. The fence
strips provider environment and denies external Python socket connections. The replay uses retained
parsed decisions/usage and saved requests, not unavailable original encoded response bodies. It leaves
the old wrong index unchanged. Constructed correct answers test publication/annotation arithmetic only.
Run new tests with the existing `check-study-offline.py` supervisor and a separate PG test schema;
the report records the actual selection. Stop the dedicated container afterwards, retaining its volume.

## Telemetry and accounting

`DecodedMetadataTransport` streams HTTPX-decoded bytes once, caps captured decoded JSON at 128 KiB,
and presents identical decoded bytes to the frozen Channel. It supports streamed/compressed and
pre-consumed Mock responses. HTTP errors stop before body reading; their body metadata stays unknown.
Malformed, incomplete or over-limit bodies have explicit capture status, never guessed identifiers.

Call rows retain local request UUID, exact request SHA, durable ledger call ID/reservation, UTC start/end,
HTTP status, returned `model`, response `id`, allowlisted request-ID header, fingerprint and sanitized
numeric usage (including nested numeric details). Missing/invalid fields remain null/UNKNOWN. Model IDs
reported by the provider need not be immutable. Cached tokens come only from explicit hit/miss or nested
cached-token fields; missing miss is never inferred from total input. Conflicts/invalid totals are flagged;
raw valid numeric fields remain visible for audit. No arbitrary response headers, error text or bodies are
logged; identifiers and numeric field names are restricted and credential echoes excluded.

Usage metadata survives a later protocol failure. A rejected pre-send reservation resets metadata and
cannot inherit a previous response. Reviewer is rejected before any reservation or credential lookup.
Provider usage, Mock usage, rate-based calculation, local reservation/charge and supplier invoice are
separate: this recorder does not calculate a bill. Join `ledger_call_id` to `ledger.jsonl` for the conservative
legacy peak/no-cache local charge. `pricing_source` records the explicit source observation; it is not
evidence of account debits. No current pricing/balance lookup occurred in this task. First-run model/cache
fields cannot be recovered and remain UNKNOWN. Never infer them from an alias or documentation mapping.

## Same-scope real retest: NOT AUTHORIZED / NOT_RUN

Before any future `--live`, obtain a **new** numeric USD cap and acceptance of moving-alias and supplier
billing limitations. Old authorization and unused capacity do not carry over. Confirm the date-specific
public price observation is still compatible with the frozen local reservation basis. Current price and
account balance are UNKNOWN in this task. Incompatibility/staleness blocks execution; do not edit old pricing.

- Scope: `retest-plan.json`, exact original two complete sessions/eight turns; compare data/plan/candidate hashes.
- Old Agent: `p8-tutor-python-notation-v10-development-r2`; new Agent: `p8-tutor-grounded-v11-development`.
- Same requested model `deepseek-flash`, endpoint, thinking disabled, temperature 0, max output 1,200;
  returned model/version remains unverified until separately authorized responses. Alias drift and sampling
  nondeterminism can confound comparisons even if both return the same string.
- Reviewer off, concurrency 1, SDK/transport/application transport retries 0; retain bounded format/mode
  repairs. Minimum normal 16 requests; optional second searches 24; absolute maximum 40, including failures
  and repairs. All money and session/turn bounds remain enforced before dispatch where previously enforced.
- USD amount: **UNCONFIRMED**. Future invocation must explicitly supply `--max-usd <NEW_APPROVED_USD>`
  and `--max-calls 40`, fresh output, current `--pricing`, live opt-in and the ledger/bill-cap acknowledgment.
  No runnable unbudgeted live command is provided. Local pre-reservation is not a supplier invoice hard cap.
- Stop on first transport/auth/model/protocol failure, budget/call cap, pending/blocked accounting; preserve
  failures and all eight expected denominators. No model fallback, auto-resume, top-up or silent rerun.
- Differences: generic prompt, versioned adjacent-source passages/derived citation IDs, decoded telemetry,
  synthetic owner/run namespace and code/manifest SHA. Prompt/schema/context byte changes also affect costs.
  Persistent sender, accounting, scoring, parser, dataset, learner messages and product defaults are unchanged.
- Review all eight against original lines, retaining incomplete/incorrect outputs and citation denominators.
  No quality pass follows from mechanics. These development cases have now informed tuning, so any improvement
  is not generalization evidence. No SQL/60/320-turn run is authorized.
