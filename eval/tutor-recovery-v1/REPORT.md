# Tutor early-stop recovery and quality diagnosis

**The original budget guard was correct.** The seventh turn exhausted its
**per-turn serialized-context reservation**, not the batch's money/request cap.
The avoidable pressure came from preparing a format repair with all 12 retrieved
passages although the rejection instructed a rewrite using four kept sources.
The additive v12 candidate projects only that repair view; it keeps every cap and
authority check. Fixed-response PostgreSQL regressions demonstrate that the known
checkpoint can now repair within the original limit. **Real post-fix quality and
cost changes remain NOT_RUN.**

This task made **zero real model, embedding or reviewer requests**, read no provider
credential values and reused no expired spending authorization. No model endpoint,
pricing/account endpoint, SQL holdout, production/student data, other workspace,
CI, product default, push, PR, merge or deployment was used or changed.

## Identity and evidence boundary

Work began clean at `14a694ae65b82a2e54b6b708796b3a5ebc517fef` on
`codex/tutor-scale-preparation`, in the requested worktree. The old real execution
version remains `06b5858024b5b22cded0573dca7963c5a73b3d19`.

The **actual final verification version** is
**`8219686e9fbd34610e10f549b523329171c58bac`**, with explicit identity
**`p8-tutor-repair-context-v12-development`**, entry point
`lecturelens_real_eval.tutor.repair_context_runtime:RepairContextTutorRuntime`.
Its manifest SHA-256 is
`4540369887eb2d84f79ee5351a8e1c0c82af859be8ff8d364ce7faf262a3afb2`.
It chains the unchanged v11 manifest
`b7fe50df1854703cc05d4ad039dad3245cc62adc5d68c3af7b394f2407f0ec58`.
The old v11 source, manifest chain, fresh-development freeze, questions, reference
answers, rubric and scores still validate. No old hash was replaced to accept a
behavior change. The original runtime remains importable and is tested alongside
v12; neither class registration nor product routing changed.

Original evidence remains under `.data/tutor-fresh-live-20261107/`. All **62**
files in its manifest and **2,011** previously recorded allowed tracked-file hashes
were rechecked unchanged. Its **34 PG ledger events, two sessions and seven turns**
were compared by full content with the original export after testing. Protected
SQL/mixed-scope files were not opened. New evidence is separate:

`/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens/.data/tutor-recovery-v1-20261107/`.

The original run did **not** retain complete raw provider response bodies. Replay
therefore reconstructs explicitly synthetic HTTP envelopes from the retained
parsed tool calls, dropped-call count and allowlisted response/model/usage/cache
metadata. It does not claim recovery of original response bytes, headers or
unrecorded fields. All **17 original request bodies match byte-for-byte**, all six
completed answers match, and the same seventh-turn failure is reproduced through
the unchanged channel, persistent store and v11 runtime. This is stronger evidence
than relying on the previous report's root-cause explanation, but it is still
fixed-response mechanics, not a new model trial.

## Reconstructed seventh-turn trace

The learner asked where to keep richer notes for the next handoff after an
importer split embedded line breaks. The model searched twice, observed 12 unique
passages, then proposed a finish with **five** distinct citations and **1,601**
characters. The hard limits are four IDs and 1,600 characters. The proposal's IDs
were all observed; no ownership, source-version, HTTP or usage failure caused this
stop. A 515-token output can still exceed a character limit, especially with
repeated 64-character IDs: output tokens and response characters are different
constraints.

| Original request | Model decision | Runtime reservation units | Cumulative turn units | Ledger reserve, nano-USD | Ledger settlement, nano-USD |
| --- | --- | ---: | ---: | ---: | ---: |
| 15 | Search for richer explanation/separate documentation | 6,992 | 6,992 | 3,216,300 | 503,700 |
| 16 | Search for separate comments/metadata/formatting guidance | 17,078 | 24,070 | 6,228,000 | 1,308,600 |
| 17 | Oversize five-citation finish | 20,983 | **45,053** | 7,407,300 | 2,200,200 |
| Proposed repair, **not sent** | Finish-only correction observation | **23,897** | **68,950** | No ledger reservation | No charge/event |

Runtime units are `len(JSON([messages, schemas]).encode(UTF-8)) + 1200` per decision,
accumulated persistently. They are a byte proxy plus output allowance, not provider
tokens. The paid channel separately reserves serialized wire bytes at its frozen
peak-input basis plus maximum output, then settles from known usage. Unused
runtime reservation is intentionally not refunded from that independent counter.
Neither cached input discounts nor low settled USD replenish turn context units.

| Constraint | Original observed state | Did it stop the turn? |
| --- | --- | --- |
| Authorized total / effective local money cap | USD 10 upper limit / USD 0.70 local ledger envelope | No |
| Frozen part A / B allocation | 40 calls + USD 0.35 each; B never started | No |
| Actual total / part-A calls and settlement | 17 calls, USD 0.0226524 local settlement | No |
| Session call limit | 5 used / 60 | No |
| Session context-proxy limit | 66,864 used / 640,000 | No |
| Turn model slots | 3 used; normal limit 4, prepaid repair limit 5 | No |
| Turn searches / tool slots | 2 searches; 2 tool slots used before finish rejection | No |
| Turn context-proxy limit | 45,053 used / 64,000; 18,947 remaining | **Yes: repair needs 23,897, deficit 4,950** |
| Ledger health | pending 0, blocked null, PG/JSONL identical | No |
| Deadline | Still in the future when failure was committed | No |

The runtime recognizes the format violation, authoritatively reads every proposed
ID, prepares a repair observation, and tries to prepay its next request in the
same transaction. `reserve_call(..., repair=True)` rejects 68,950 > 64,000.
The transaction rolls back, so **no repair observation, extra call/tool count or
fourth model request commits**. The last received response remains in the failed
checkpoint; the public answer stays null. This explains why the original journal
has the rejected proposal but no committed repair reason. The targeted replay
reproduces this sequence rather than inserting a missing journal event.

This is normal fail-closed accounting applied to an inefficient repair payload,
not evidence of a ledger arithmetic bug, exhausted USD authorization, or a need
to enlarge all limits. The execution sheet explicitly warned that nested runtime
bounds could stop before the theoretical 80-call envelope. The smaller answer
limits and larger API token setting are distinct controls, not interchangeable
configuration values. No paid limit or retry count has been increased.

The old adapter raises `PILOT_STOPPED_ON_FAILURE_OR_UNKNOWN_OUTCOME` after the
failed turn, returns an incomplete part, and the frozen batch wrapper breaks
before B. Reconciliation retains 16 scheduled positions: **6 completed / 1 failed /
9 missing**. That whole-batch stop **complied with the original explicit contract**.
It is not retroactively called a scheduler bug or changed to a successful trial.

## Minimal fix and independent-session protocol

The new runtime adds one request-preparation override. For a committed/pending
`TUTOR_FINISH_REPAIR_REQUIRED`, it:

1. Uses the inherited request preparation to re-READ the entire authorized union.
2. Validates the journal's `keep_ids` and projects only model-facing Evidence to
   those sources, preserving their exact text and order.
3. Preserves full selected-ID authority, history, summary, search observations,
   repair details and schemas; accurately describes the smaller repair view.
4. Reserves the actual projected request using the unchanged formula and limits.

For this checkpoint, **12 → 4 passages**, repair **23,897 → 16,422** units, and
turn total **68,950 → 61,475**, leaving **2,525** units under the same 64,000 cap.
Ordinary requests are identical to v11. There is no content truncation, automatic
citation reassignment, answer rewriting, prior-budget refund or extra repair
chance. A request that still cannot fit continues to fail before send. Ownership,
version/deletion, cancellation, unknown-outcome and prepaid restart guards remain.
A deleted fifth source is still detected before it could be hidden by projection.

The synthetic successful repair is deliberately short and lacks the full original
multi-part teaching answer. It demonstrates publication/recovery mechanics only;
it is **not** a replacement real answer or a quality pass. The inherited first-four
steering can lose an important fifth source (here, metadata guidance); a real
revision might omit required content or refuse. The fix does not claim to solve
that semantic tradeoff. All required-point scoring still applies.

A separate **Mock-only** `session-isolated-v1` driver makes the proposed evaluation
failure scope explicit. It does not alter the frozen v11 runner or product:

- Enumerated local format/mode, turn/session-budget or deadline failure preserves
  the failed turn, leaves the rest of that conversation missing, and permits a
  later independent session with empty history/summary.
- Global call/money limits, missing/unknown/pending/blocked/divergent accounting,
  auth/model/protocol/authority failures, cancellation and unclassified failures
  stop all sessions. Unknown accounting is null, never zero. Existing reservation
  guards remain the final authority before every send.
- No dependent turn is resumed with an invented antecedent. Even later apparently
  independent topics in the same failed conversation are conservatively skipped;
  complete-session boundaries are the execution unit.
- All 16 expected positions are written before dispatch and remain in failure,
  missing and coverage denominators. A batch with failed/missing turns cannot pass.
  Hitting a global cap exactly on the final planned successful response does not
  make an otherwise complete run incomplete.

The driver requires the socket fence and an explicit Mock transport, sets
`live=False`, and has no live CLI. Its single Mock ledger/protocol is new; historical
A/B allocations are not silently pooled or transferred. A future real adapter must
freeze its allocation/stop policy and receive new authorization separately.

## Six-answer quality diagnosis

**Original labels are unchanged.** Complete correct is **3/16** for batch delivery
and **3/6** conditional on completed answers. Among completed answers: three correct,
two incorrect and one uncertain. Core required points are present in all five
completed answerable turns; optional false/unverified additions prevent three
full-answer passes. This is Codex nonblind review, not independent human agreement.

| Completed answer | Evidence-backed diagnosis | Minimal action / remaining uncertainty |
| --- | --- | --- |
| Python tail 1 | Correct `n`, `e`, `xyge`, but falsely says the unit does not explicitly provide `[-1]`/`[-2]`. Original 512–522 explicitly prints them. The output passage 517–529 ranks **10th / 34th** for the actual two queries; neither enters top eight. A Solution heading separates the question from output, and lexical ranking ignores short/numeric symbols. No prior context is involved. | Retrieval coverage gap and false generated scope claim are confirmed. Whether better retrieval prevents that claim is **unverified**. A generic exercise/solution grouping experiment is a future proposal, not a proven semantic fix. No ranking, query-specific hint or reference answer is hardcoded here. |
| Python tail 2 | Correct suffix and `try`/`hi` results with prior context retained. Required source is already observed. The model adds “only works for oxygen” about `[3:6]`, contradicted by any suitable other six-character string, and locally cites the question/interior-slice passage for its later suffix explanation. | Generation/source-attachment defect, not missing required retrieval or observed parser rewriting. No evidence that more prompt instructions fix it; keep pending real-model verification. |
| Python tail 3 | Correct no-padding answer and prior `hi` result. The phrase attributed to the course as “when available” appears in the learner request, not the cited course passage. | Original uncertain judgment retained. Learner/source attribution confusion is visible, but its internal cause is unknown. No relabelling as a pass or a wrong suffix output. |
| Python tail 4 | Clean canonical refusal; no Unicode algorithm invented. One extra parallel search proposal was ignored and recorded, without an extra paid request. | No established defect requiring a fix. Other expected refusals remain missing in the full-batch denominator. |
| Python tail 5 | Complete lesson-specific IPython/Jupyter and plain-interpreter discovery/help workflow; requested transition handled. | No established defect. Do not infer verified completion setup on every learner machine. |
| Spreadsheet text 1 | Both export failure classes and simple-cell restriction present. Final concrete strip/replace suggestion has no local citation; no actual repair/losslessness claim is established. | Original correct task label retained, but the optional uncited suggestion remains in coverage. No demonstrated parser removal or need for an importer-specific recipe. |

The reconstructed channel/runtime reproduces all six published answers. No parser
rewrite or loss of a supplied citation is observed in available records. Complete
raw response bytes are unavailable, so unrecorded response details are not asserted.
Only the execution-context fix has a demonstrated causal mechanism and targeted
counterfactual test. There is no evidence-backed automatic semantic patch for the
generation/source-attribution defects; adding per-question hints or filtering
answers to manufacture higher scores would not establish quality improvement.

Citation ratios apply to the **six completed published answers**: **18/21** supported
substantive pairs; citation presence **21/25** and supported claim coverage **18/25**
over 25 citation-requiring assertions (29 distinct assertions total). Failed drafts
and missing turns have no published content to annotate. They remain in **16**
scheduled task positions and **12** expected-answer positions; fully supported
expected-answer coverage stays **1/12**. The original failed draft remains a
separate diagnostic, never a successful answer. No scoring correction was justified;
original labels and the uncertainty judgment are preserved, with their subjective
Codex-review limitation visible.

## Verification and cleanup

At clean code commit `8219686`, the supervised final check completed in **83.598 s**:
**184 passed, 0 skipped, 0 failed** — 42 new recovery tests, 20 frozen fresh-batch
tests and 122 inherited Tutor mechanism tests on real isolated PostgreSQL schemas.
Ruff check/format passed for new files using the Agent service configuration.
One existing Starlette/AnyIO deprecation warning remains unrelated to this change.

| Verification | Result and meaning |
| --- | --- |
| Original v11 batch and retained response replay | 17 exact original request hashes, six unchanged answers, same 6/1/9 stop; original frozen entry also independently reproduced before the fix |
| v12 prefix plus explicit synthetic repair | Same first 17 requests; one synthetic eighteenth response publishes within 61,475 units; nine remaining positions intentionally missing at a Mock-only cap. **Not a real quality improvement** |
| Exact turn/session call and byte-proxy boundaries | Fits exactly; one unit/slot over fails before repair dispatch, with no committed repair observation |
| Repeated invalid format | One repair response, then `TUTOR_FINISH_FORMAT_INVALID`; no additional repair purchase |
| Prepaid restart / cancellation / deleted authority / unknown reserved outcome | Counters not charged twice; no resend of unknown outcome; cancellation/authority fail before extra provider call |
| Independent-session local failure | Synthetic first-session format failure: **11 completed / 1 failed / 4 missing**, subsequent three sessions start empty; no fabricated dependent turns |
| Auth, timeout, protocol, missing usage, usage beyond reservation | Exactly one Mock send, then **0/1/15**, no retry/next session; failed/unknown usage retains reservation |
| Call cap / tiny money envelope | No extra send; money can fail before any reservation/send; **1 failed / 15 missing** retained |
| Pending/blocked/divergent/unknown accounting | Global stop; divergence preserved, accounting UNKNOWN rather than zero |
| Exact global cap on final scheduled response | 16 mechanically complete, zero failed/missing; quality still NOT_RUN |
| Historical isolation | Original 62 artifact hashes, 2,011 allowed tracked-file hashes, 34 PG events, two sessions and seven turns unchanged |

The initial draft check had **59 pass / 1 fail** from a test comparing an unescaped
answer with serialized JSON. The parsed history was correct; the assertion was
corrected to compare decoded fields, without a runtime change. That failed log/XML
is retained. A subsequent development check passed 183 tests. A final boundary
check was added and the new offline driver's final-cap completion classification
corrected before freezing code; final 184-test evidence is authoritative. None of
these unit-check iterations represents a new real evaluation or changes old scores.

The launcher stripped provider/proxy environment and installed the existing
external socket fence. Final fence counters show zero external attempts; libpq
connections bypass Python socket counters, so actual PostgreSQL test execution,
row comparison and ledger checks supply DB evidence. No host-wide packet audit is
claimed. Only the previously stopped dedicated container on loopback 25841 was
started (pinned image, sole volume consumer, no dependencies, 0.5 CPU/384 MiB).
It is now **exited 0**, port closed, volume retained, and all **23** preexisting
containers remain running. Temporary per-test schemas were dropped; the separate
original-reproduction export/schema and files are retained as evidence.

Evidence includes `root-cause-verification.json`, `reproduction.json`,
`v11-reproduce/`, `v11-reproduce-pg.json`, `context-measurement.json`,
`quality-analysis.json`, `checks-frozen-evidence/`, `frozen-tests.xml`,
`checks/recovery-frozen.{json,log}`, `network-frozen/`, `preflight.json`,
`cleanup.json`, plus retained draft/development checks. The non-sensitive
[verification summary](VERIFICATION.json) records identities and evidence hashes.

## Minimal next real-test plan — not executed

Recommend **a new full 16-position development regression from fresh sessions**,
not a selective replay of the failed/missing tail and not a splice of old v11
successes with new v12 outputs. These questions are now consumed development data;
a new run must not be called fresh independent holdout evidence.

Before spending, freeze a **new real adapter/run contract** around the explicit
v12 identity and chosen session-isolated stop policy. Preserve the existing source
and rubric hashes, order, all 16 positions, complete-session boundaries, budgets,
reconciliation and failure/missing census. The current Mock-only driver rejects a
real transport and is not that authorized live entry. Explicitly freeze whether
one global ledger or fixed part allocations apply; never silently pool historical
A/B allowances. A conservative proposal can retain **at most 80 requests and the
existing USD 0.70 local ceiling**, with fresh pricing and a new explicit budget
grant. Neither the old USD 10 grant nor this proposal authorizes calls. Keep the
same requested alias/settings, reviewer off, concurrency one, transport retries
zero and existing bounded repairs; record alias/immutable-version uncertainty.

Run once, retain all failed/missing positions, then apply the unchanged semantic
and citation gate to the whole new trial. Report execution completion separately
from complete correctness, including both scheduled and completed-answer
conditional denominators. This can measure a development regression, including
whether real repairs still omit necessary points or make false source claims.
Candidate, execution protocol, possible call count, randomness and a moving model
alias differ from v11; any observed change is not an isolated causal estimate of
the context projection. Fixed-response replay only isolates mechanics. Independent
fresh held-out data would be needed for a later generalization claim, under a
separate task/authorization; do not consume SQL or expand scale now.

**Remaining blockers:** real v12 repair behavior and task quality are unmeasured;
source-attribution/exclusivity and retrieval coverage defects remain; the kept-four
repair can omit required metadata; the next live adapter/protocol is not yet
frozen/authorized. **NOT_RUN:** post-fix real quality, real cost change, independent
human agreement/kappa, SQL holdout, expanded evaluation/300 turns, learning effects,
new-course generalization, supplier invoice verification, live reviewer/embedding.
