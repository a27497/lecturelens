# v12-session-isolated-live-v1

This is a new execution protocol around the unchanged v12 runtime. It does not
replace the old v11 stop-on-first-failure contract or the previous Mock-only v12
protocol. The scope remains four complete sessions / two development courses /
16 scheduled positions in their original order. No SQL input is loaded.

## Startup and accounting

Before directory creation, DB connection, transport construction or credential
lookup, verify the v12 manifest chain, this adapter lock, fixed run-plan hash,
original input hashes, all data/source locks, exact 16 keys and explicit Agent,
model, reviewer and concurrency settings. Missing/mismatched input refuses startup;
there is no fallback. Preparation is the default and does not require a database.

Execution requires explicit 1–80 total requests and a positive integer nano-USD
envelope at most USD 0.70. No default cap grants spending authority. This protocol
uses **one new global ledger**, unlike the old batch's fixed A/B half allocations;
there is no historical balance/allowance transfer. Keep the existing pre-send
reservation, mirroring, fsync, no-pending-call and single-use guarantees. All failed
and repair attempts consume their normal reservations. Missing usage is unknown,
not zero or a refund. Local enforcement is not a supplier invoice hard cap.

The nested runtime limits remain 64,000 serialized-context proxy units per turn,
640,000 / 60 calls per session, two searches per turn, one format repair and one
mode repair. Normal call slots remain four, with a prepaid fifth repair slot.
No unit here increases those limits or changes the 1,600/500-character/four-ID
publication schema. A global money/request limit is never a local turn budget.

## Classification and propagation

Apply these rules in order after capturing the current synthetic-scope PG record.
The channel also stops immediately on decoded usage/cache accounting anomalies,
before a second model decision can occur. Channel failure/unknown usage overrides
any nominally local runtime error; checking only `pending == 0` is insufficient.

| Condition / exact code | Scope and action |
| --- | --- |
| Invalid/unknown/pending/blocked/divergent ledger | Stop all; unknown accounting remains null |
| Failed channel call, missing/invalid usage, telemetry anomalies | Stop all; includes auth, model-unavailable, transport timeout, parser/schema and fabricated-source errors |
| Global call/money cap reached or reservation refused | Stop all; never top up, resume, transfer or retry |
| `TUTOR_REPAIR_BUDGET_UNAVAILABLE` | Local turn/session repair reservation; close this conversation |
| `TUTOR_BUDGET_EXHAUSTED` | Local runtime turn/session call, tool or byte-proxy bound; close conversation |
| `TUTOR_FINISH_FORMAT_INVALID` | Local repeated size/ID format violation after existing one-shot repair |
| `TUTOR_SOCRATIC_CONTRACT` | Local repeated supported-outcome/question violation after existing one-shot repair |
| `TUTOR_DEADLINE` | Local runtime deadline; channel timeout/unknown outcome still stops all |
| Any other failure, cancelled/nonterminal turn, exception or interruption | Stop all conservatively |

The five local codes come from the existing runtime's bounded execution paths,
not prefix matching. Citation mismatch, stale/deleted/foreign evidence, unknown
reserved outcomes, cancellation and unclassified errors are **not** local.
Captured channel failures and global accounting/caps take precedence even if a
runtime code happens to match that local set. A safety failure is never swallowed
to improve completion.

After a local failure, keep its failed record and stop the rest of that complete
conversation. Traverse the original dependency inventory: mark later positions
`SKIPPED / DEPENDENCY_FAILED_OR_SKIPPED` with their failed/skipped predecessors
and root failure. A later topic with no such dependency is conservatively marked
`SKIPPED / SESSION_CLOSED_AFTER_LOCAL_FAILURE`, not falsely described as dependent.
Do not construct a substitute answer or continue with an invented antecedent.
Only a subsequent independent session may start, with new scope/session ID and
empty history/summary. It shares the same global ledger and remaining bounds.

After a global stop, unattempted positions are `MISSING / GLOBAL_STOP_BEFORE_TURN`
with the stop reason. Capture attempts before execution; retain a known attempted
ID with status UNKNOWN if its PG result cannot be recovered. Such attempts count
as failed/unresolved, with a separate unknown subset, never completed. Accounting
failures never reset the ledger. No automatic resume or resend is supported.

A cap reached exactly on the final successful scheduled response prevents further
dispatch but may still yield mechanically COMPLETE if all 16 responses completed
and accounting is healthy. This is not a quality PASS.

## Citation and evidence invariants

The unchanged v12 runtime authoritatively re-READs the full selected-ID union
before projecting the format-repair view to the rejection's kept sources. The
checkpoint's full selection, history, observations and source identity survive.
No citation is renumbered, rebound to different text, or silently discarded by
this adapter. Publication still checks observed IDs, ownership, revision and
source validity. Request evidence has bounded model-facing fields; canonical
citations retain the original source text/member provenance for review.

Evaluation capture may read its own newly created synthetic PG turn after a
runtime authority failure so the failed record is not lost. This diagnostic read
cannot publish an answer or authorize an ID and checks exact owner/course/session
scope. It never reads unrelated runs or business/student data.

## Fixed comparison and scoring units

Use the unchanged original `grading-rules.json`; no Mock labels enter real scores.
Report both **verified complete correct / 16 scheduled** and **verified complete
correct / C completed** (null if C = 0). Failed, uncertain, skipped and missing
outputs are not passes. Report completed, failed/unresolved, skipped and missing
as disjoint categories summing to 16; attempted = completed + failed/unresolved.
Also report scorable/reviewed, unknown-attempt subset and unexecuted = skipped +
missing. Old results did not distinguish explicit skips: compare their nine
unexecuted positions without rewriting them as a new protocol trial.

Citation support = supported substantive claim–citation pairs / all annotated
pairs, including uncertain. Presence/support coverage uses every citation-requiring
assertion in complete inventories, including uncited and material optional claims.
These content ratios concern completed published answers and must state that
scope. Expected-answer full supported coverage keeps **12** scheduled answerable
positions; failure, skip, missing and wrong refusal cannot improve it. Zero labels
or pairs are NOT_RUN/null, not PASS. The strict gate still requires all 16 completed
and reviewed, in addition to every unchanged correctness/citation threshold.

The original v11 result remains 3/16 batch correctness and 3/6 conditional
correctness; citation support 18/21 and supported coverage 18/25 concern its six
completed answers, with full expected-answer coverage 1/12. New values remain
NOT_RUN until a newly authorized full run and source review. Candidate and stop
protocol both differ from v11: completion changes are not pure answer-quality
improvements. Never splice old successful answers into the new run, selectively
rerun its failed tail, or claim this consumed development set is a fresh holdout.
