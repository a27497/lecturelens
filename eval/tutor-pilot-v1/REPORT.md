# Pilot preparation validation — 2026-11-07

**Prepared for confirmation, not authorized to spend.** No real Tutor, embedding, reviewer, model-list or
account/billing request was made. This is a Codex implementation/mechanism check, not human annotation.
Started at clean `3479b095cee93266fa3404edea76d546a1e949cc` on `codex/tutor-scale-preparation` in
`/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens`. No other worktree/private account configuration
was inspected. Read AGENTS.md, the frozen pilot contract/report, public Mock driver, synthetic live pilot,
runtime repair limits, channel/ledger and recorded metadata before adding this evaluation-only adapter.

## What was missing and what was reused

The public driver cannot execute live. The existing synthetic live pilot selects v9, a different dataset
and automatic reviewer calls. Added only `eval/tutor-pilot-v1/`: a single-purpose driver/guard, its tests,
independent adapter hash lock, dated public-price observation and execution checklist. The new driver
reuses historical scope/identity verification, channel, global mirrored ledger, authoritative local search,
store/provider and missing-result reconciliation. It directly selects **v10-development-r2**, exactly the
frozen two complete development sessions/eight turns; no SQL is registered with the candidate runtime.
Reviewer routing rejects before reservation/credential lookup, and missing review is never quality success.
The default command only prepares: no DB, transport construction or provider credential lookup.

The unchanged channel fixes Tutor ID `deepseek-flash` and route `https://api.deepseek.com`. Public pricing
and changelog inspected on 2026-11-07 identify the current version as `DeepSeek-V4.1-Flash-1017`, reached
through a moving alias. An immutable request ID is **not verified**; reported response metadata cannot
prove a backend version pin. Availability is **pending first separately authorized real request**.
[README.md](README.md) records official links, prices, limits, pending confirmations and a placeholder-only
live command; [the observation](pricing-observation-20261107.json) is not spending authorization.

Normal model HTTP requests: **16** (search/finish × eight turns); with a second search: **24**; with both
existing finish repair categories: **40** maximum. Reviewer calls are zero, application transport retries
zero, HTTPX transport retries zero, no SDK or redirects. Local tools do not generate embedding/provider
search requests. One global ledger covers both sequential sessions rather than splitting budget by course.

The ledger reserves request bytes at verified peak cache-miss input rates plus maximum output before send,
checks mirrored PG/JSONL **content**, and blocks pending/unknown outcomes or exhausted limits. Failures
retain at least the reservation. It is an enforceable **local reservation/estimated-cost cap**, not a proven
supplier bill hard cap: byte/token framing is not guaranteed, usage can be unknown, and rates/alias can
change. An overshoot stops later requests after the affected request. The inherited USD 0.70 maximum is a
technical ceiling, not an approved budget. Account balance/provider-side cap remain UNKNOWN/UNVERIFIED.

## Actual checks

| Version | Verification | Result |
| --- | --- | --- |
| `d47675ed701bc77ed22d187fe3421313dea363fc` | New pilot tests 22 plus three relevant inherited ledger/channel tests | **25 passed**, zero failures/errors/skips; 16.28 s |
| `66f23acfb76ba4cbd38f1033caf93bd93bcc07cd` | Saved-price-date reproducibility and default no-egress preparation | **2 passed**, zero failures/errors/skips; 0.56 s |
| Both | Ruff lint/format; final read-only prepare after DB stopped | Passed |

The second commit changes only the test's observation clock and its adapter hash; `pilot_run.py`, pricing,
scope and Agent bytes remain identical. No broad/full historical suite was repeated. Final delivery adds
only this report and VERIFICATION.json to `66f23ac`; the tested execution implementation is unchanged.

Seven bounded PG/Mock runs retained expected eight-turn manifests and outputs. Independently recounted
normal/max paths completed eight turns with **16/40 reserved Mock dispatches**, zero reviewer calls.
Other fixtures verify global caps 1/8, pre-send money rejection, transport timeout, malformed/missing usage,
no retry/refund, preserved missing turns and stop before further sends. Standalone guards verify no reviewer
reservation, pending-reservation rejection, source/scope tampering, wrong Agent/model/concurrency/reviewer,
missing/invalid caps and stale/incompatible pricing. Mock asserts exact system identity, no Authorization
header, no credential lookup, and no real HTTP transport construction. Positive live checks call preflight
only, with no credential or transport access. All quality/agreement/cost statuses remain NOT_RUN.

An initial test assertion incorrectly expected every second-session row to be MISSING at cap 8. The next
local turn instead records a pre-egress budget rejection: failed then three MISSING rows, with only eight
Mock sends total. Corrected the assertion, not runner behavior or task data. The initial 21-pass/one-fail
draft record is retained. The synthetic DB fixture now redacts connection details in pytest representations.

The dedicated initially stopped DB was verified by project/compose path, pinned image, loopback 25841/free
port, sole volume consumer, no dependencies, 0.5 CPU/384 MiB limits and available RAM/disk before start.
Confirmed the synthetic role/dedicated acceptance DB, used fresh `pilot_prep_*` schemas and synthetic
owner/course IDs, then confirmed zero remaining test schemas. Restored only that container to **exited 0**;
retained its volume and all prior evidence. No product stack was started. Subprocesses ran under the existing
socket fence with provider configuration stripped and 180/60 s supervisor limits; no timeout/cleanup failure.

Independent before/after hash comparison: **540 pre-existing related tracked files unchanged**. No product
runtime/default identity, frozen prompt/data/scope/hash, prior result, original blind sample or CI was changed.
No push, PR, merge or deployment. [VERIFICATION.json](VERIFICATION.json) records exact versions/counts and
raw paths; artifacts are `.data/tutor-pilot-preparation-20261107/`, with supervisor records under
`.data/dev-checks/tutor-pilot-preparation-{draft,final,clock}/`.

## Remaining confirmations / NOT_RUN

User must confirm the exact Tutor ID/provider, accept the moving-alias limitation or require a verified
immutable alternative, reviewer off/concurrency one, zero transport retries with bounded controller repairs,
the total request cap (proposed 40), and an explicit positive USD ledger cap within the technical ceiling.
Supplier billing hard-cap protection must be independently confirmed or its absence explicitly accepted;
the account balance is for the user to check. A price observation must be current on the actual run date.
The frozen scope itself grants no spending authorization. No execution continues automatically after this task.

**NOT_RUN:** real requests/availability, real answer/citation quality, human agreement/kappa, real token
consumption/cost/invoice, learning effects, load testing and deployment paths. Mock output does not resolve
these unknowns or prove model intelligence. Await explicit paid authorization and filled execution values.
