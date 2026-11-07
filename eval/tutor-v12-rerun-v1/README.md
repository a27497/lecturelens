# Frozen v12 full-development rerun entry

`rerun.py` binds the existing `p8-tutor-repair-context-v12-development` identity to
all 16 consumed development positions from `tutor-fresh-dev-v1`. It reuses the
unchanged runtime, source projection, Tutor-only channel, PG store, ledger,
pricing check and development-only file fence. No product registration, shared
runtime, default, old runner or historical manifest changes.

- `run-plan.json`: exact candidate, original inputs, order, settings and ceilings.
- `protocol.json` / [PROTOCOL.md](PROTOCOL.md): bounded local/global failure policy.
- `adapter-lock.json`: pins this entry, verifier, plan, protocol and targeted tests.
- [EXECUTION_SHEET.md](EXECUTION_SHEET.md): preparation command and unapproved live
  template; no money/request cap defaults or inherited spending authorization.
- [REPORT.md](REPORT.md): actual no-cost preflight and validation results.

The default only verifies/prepares: no output directory, DB, transport or provider
credential lookup. Mock execution requires the existing socket-fenced launcher;
live execution is forbidden inside that fence. The live branch additionally needs
explicit caps, the independent live opt-in, new-batch/billing acknowledgments and
execution-date compatible reviewed pricing. These technical switches are not
conversational permission to spend.

Every run uses new sessions, one new global PG/JSONL ledger and a single-use output
name. There is no selection option, model fallback, resume, automatic retry or
replenishment. All 16 expected positions precede dispatch. Raw request bodies,
allowlisted response metadata, parsed proposals, observations/checkpoints,
citations, attempts, skipped/missing reasons and accounting remain locally
traceable. Credentials/headers are not recorded. Original full response bodies
were not available for historical replay; envelopes reconstruct retained parsed
fields and metadata only. Mock/reconstructed responses verify mechanics, not
post-fix model quality or actual supplier cost.
