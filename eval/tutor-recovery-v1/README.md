# Tutor repair-context v12 development candidate

This opt-in runtime changes only the evidence view for a finish-format repair.
The v11 parent, ordinary requests, source projection, product default and frozen
fresh-development questions/rubric remain unchanged. The candidate is experimental;
real post-fix quality and cost changes are **NOT_RUN**.

`RepairContextTutorRuntime` first uses the inherited authority reads, then projects
repair Evidence to the rejection journal's `keep_ids`. History, summary, full
selected-ID checkpoint, search/repair observations and schemas are preserved.
Reservation uses the projected serialized request plus the same 1,200 allowance.
The 64,000 per-turn byte proxy, session limits, output limits, repair counters,
prepaid recovery, cancellation, version/ownership checks and channel ledger remain
unchanged. A request that still cannot fit must fail. Evidence projection does not
validate semantics or ensure a shortened answer retains all requested points.

`candidate.json` chains the frozen v11 manifest and pins the new runtime and
evaluation support code. The new class has no product factory registration.
Tests are hashed separately in verification artifacts, not runtime identity.

`session_driver.py` is a **Mock-only**, socket-guarded evaluation driver, with no
live CLI or spending authorization. Its explicit `session-isolated-v1` protocol
continues a later independent session only for enumerated local format/mode,
turn/session budget or deadline failures. The rest of the failed conversation
stays missing. A global cap, unknown/pending/blocked/divergent accounting,
auth/model/protocol/authority error, cancellation or unclassified failure stops
all sessions. Every scheduled turn remains in the output denominator. Completing
the final scheduled response exactly at the global cap is still mechanically
complete. The frozen v11 batch keeps its original stop-on-first-failure policy.
This driver uses one Mock ledger; it does not change historical part allocations.

`replay_support.py` rebuilds synthetic envelopes from retained parsed tool calls
and allowlisted metadata. Raw provider response bodies were not retained and are
not claimed recovered. `test_recovery.py` requires the private prior run under
`.data/tutor-fresh-live-20261107/`, a separate PostgreSQL schema, a unique
`RECOVERY_CHECK_OUTPUT`, and the existing `eval/tutor-scale/safe_exec.py` fence.
The suite fails rather than skips if its evidence/database is missing. No original
record, answer, score or manifest is replaced.

See [the recovery report](REPORT.md) for actual verification, quality analysis,
remaining limits and a future full-batch retest proposal. That proposal is not a
live command or authorization; a new live adapter/protocol must be frozen and
separately authorized before any real request.
