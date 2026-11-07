# First-real diagnosis and no-cost repair verification

Decision: **keep evaluation bounded to the existing development pilot; real improvement is unverified**.
This is Codex source/code review and offline mechanism validation, not independent human expert review.
No real model, embedding, reviewer, pricing/account API or paid retest was called. Previous paid authority
was not reused. SQL questions were not inspected for tuning and no SQL candidate session was executed.

## Evidence and diagnosis

Started clean on branch `codex/tutor-scale-preparation` at
`e770d613282144fb916411676b60bfa24e9e21f8`. Read AGENTS.md, product contract, first-real/pilot/public
documentation, frozen prompt/runtime/channel/authority/identity implementations, original eight answers,
all retained parsed proposals and PG checkpoints, serialized requests, response frames and original materials.
The first real trial ran code `c41245b`; it remains the baseline. Full encoded provider response bodies
were not retained. The replay reconstructs envelopes from retained parsed decisions/usage only, with
unavailable model/cache/association fields absent rather than invented.

Source locations below refer to frozen original Markdown under `eval/tutor-public-v1/materials/`.
The new offline audit asserts all original PG answers and eleven search observations equal the retained
answers and reproduced original lexical results, then records before/after passage IDs and locations.

| Turn | Confirmed source/trace facts | Classification and limits |
| --- | --- | --- |
| Python 1 | Original search observed loading and assignment blocks, lines 31–99. The first finish used seven IDs. Controller kept the first four; the second finish dropped assignment citations but retained the claims and added “unit doesn't cover anything beyond loading and assigning.” Lines 238–260 and 296–311 contradict that scope assertion. | Grounding lost during model format repair; source selection initially contained the needed material. Controller explicitly instructed removal/re-attribution of unsupported claims, so this is not evidence of an absent repair instruction. Fixed first-four policy creates citation pressure; semantic compliance remains a model limitation. No semantic answer rewrite is introduced. |
| Python 2 | Both searches omitted 149–158 (`dtype`, `float64`, floating-point explanation); 142–147 was present. The answer correctly rejects ndarray ⇒ integer, but cites that paragraph for a dtype API it does not name and omits the reference result. | Reproduced fragmentation/ranking deficit plus generation/grounding gap. The question's wording is less specific than the frozen dtype-result rubric; omission against that rubric is distinct from falsely asserting integers. Historical grade unchanged. |
| Python 3 | Observed rows/patients, shape and generic slicing caption 240–244; explicit ordinal mapping 194–219 absent. Only one search executed despite a second being available. Final parsed proposal already contains `data[30, 20]`; published answer retains it exactly. Source 202–219 supports the frozen `data[29, 19]`. | Retrieval/decision/generation issue, not bracket parsing or a code transformation. “Patient 30” also permits a label reading; the answer's everyday-counting explanation is internally confused. Cannot isolate a single causal prompt defect from one trial. New context alone still misses 202 under the old generic query; a targeted counting query retrieves it. |
| Python 4 | Canonical refusal; no observation of the learner's laptop or compatibility guarantee. | Appropriate evidence insufficiency; preserve it. |
| Sheets 1 | Search saw tab explanation 58 and summary 330–340, but omitted the two-risk paragraph 62–65 and new-column advice 67. Answer omits inconsistent-formatting risk and gives an uncited reasonable redesign. | Retrieval omission and answer completeness/coverage gap. The unit gives the general new-column principle, not a detailed date-column recipe; do not turn the caveat into another false statement. |
| Sheets 2 | Repeated-header and new-column text observed (67–71), but freeze alternative 73 absent. Answer includes the correct freeze advice without support attached. | Adjacent-context retrieval gap plus unsupported-at-publication detail; not a false recommendation. The illustrative explanation does not prove an actual workbook's row count. |
| Sheets 3 | Both false row associations (41–47), tab recombination (62–65) and new-column advice (67) observed. Same scenario maintained. | Some evidence was present yet not attached to the comparison; extending the tabs-specific quote to side-by-side tables remains uncertain. More context cannot by itself prove semantic support or cure generation. |
| Sheets 4 | No actual workbook supplied; illustration cannot establish its exact error count. | Appropriate refusal; preserve it. |

The existing label inventory's exact answer spans and supporting source quotes were independently checked
again; arithmetic is reproduced in `baseline-recheck.json`: 8 turns, 34 claims, 31 citation-requiring claims,
24 explicit claim–citation pairs, 22 supported pairs, 24/31 presence and 22/31 supported coverage. Existing
strict completeness remains 4/8 under its original Codex labels, with the ambiguity caveats above. These
are baseline labels, not post-fix scores or independently blinded human judgments. No rubric/data/grade changed.

Metadata diagnosis is narrower than “the provider omitted model”: both old raw-byte tees failed JSON
parsing while the sender parsed decoded responses. Offline gzip fixtures reproduce that defect.
Actual production encoding/header/body is unavailable, so the specific first-run trigger is UNKNOWN.
Historical actual model, fingerprint, provider request/response IDs and cache breakdown cannot be recovered.

## Minimal changes and preserved behavior

- New explicit development identity `p8-tutor-grounded-v11-development` chains v10-r2 and historical pins.
  No old source/manifest/default is changed. The fixed-scope adapter is a versioned derivative of the frozen
  pilot; persistent sender, tool limits, repairs, store, policy, ledger, scorer and parser are reused.
- Evaluation `PassageAuthority` groups adjacent original prose/code/output into bounded source passages,
  preserving exact text/member hashes/locations with new derived IDs. This addresses a demonstrated context
  fragmentation defect. No references, expected labels, task-specific answer or new course is added to requests.
- Generic guidance covers every requested part, ordinal versus literal labels, targeted evidence checking,
  task-critical facts within four citations and preserving support during format repair. It is not a semantic
  correctness check and cannot guarantee index conversion, complete answers or faithful repair.
- Decoded telemetry records restricted provider identifiers, association IDs, numeric usage/cache details,
  request SHA and durable reservation ID, including protocol failure after valid usage. Invalid/missing data
  remains explicit; no cache miss is derived from total input. Arbitrary bodies/headers and credential echoes
  are excluded. See README for field and failure semantics.

Provider usage, local reserved/charged nano-USD, rate-calculated cost and supplier bill remain separate.
The inherited ledger still conservatively uses its frozen peak/no-cache basis and charges unknown failure
outcomes at least the reservation. This task did not verify current rates, balances or invoice. Historical
58565 input / 3618 output tokens remain provider-reported baseline usage; replaying those values in Mock
does not consume those tokens again. No post-fix real consumption or cost delta is measured.

## Verification

Final verification details and SHAs are recorded in `VERIFICATION.json`; raw evidence remains under
`.data/tutor-repair-v1-20261107/`. Verification is bounded, isolated and no-cost. Dedicated PG was rechecked
before start: correct project/compose/image, sole named volume consumer, empty dependencies, free loopback
25841, 0.5 CPU/384 MiB, about 13 GiB available memory and 44 GiB disk. Tests use their own synthetic schemas;
the pilot uses a fresh owner/run namespace. The container is restored to its initial stopped state afterwards.

The first targeted test pass found a test-only mismatch between inherited authority and Tutor exception
classes (32 passed, 1 failed); corrected the test rather than changing authority behavior. A broader test
selection was deliberately interrupted after 129 passes before public-all/holdout-oriented fixtures ran;
the final selection excludes that public suite. Both incomplete attempts and supervisor logs are retained.
No interrupted attempt is reported as a complete pass. Any subsequent implementation-specific rechecks
are identified separately in VERIFICATION.json.

At `b8e4777e9660c4051d3056bd68941215260d708c`, **374 tests passed**, none skipped. Code review
then removed an unnecessary decoder chunk buffer to preserve the sender's per-chunk elapsed-time guard
and marked an early-closed body explicitly incomplete. At final implementation
`862abe9f31105e57b79a428fa2d3cdd331e76f00`, **157 targeted tests passed**, none skipped, including
the new incomplete-stream test, decoded telemetry, paid-channel Mock mechanisms, old pilot guards and
historical identities. The context/runtime/parser/scoring code did not change after the 374-test pass.
One existing Starlette/AnyIO deprecation warning was emitted; no environment gap or skipped PG test.

Required evidence includes the final relevant Python/PG regressions, historical identity/freeze checks,
all-four Python indexing/slicing fixtures and ordinary QA/refusals, constructed annotation arithmetic,
streamed/identity/gzip/deflate/pre-consumed responses, missing/invalid/cache-conflicting usage and later
protocol failures, cap stops before send, reviewer rejection, default preparation without DB/credentials,
20 retained parsed-response replays, and one persisted eight-turn Mock with the exact original scope.
Correct fixed answers are hand-constructed contract fixtures; they do not show what a model will generate.
Old wrong answers remain wrong in the replay. Mock has no automatic real quality pass or human agreement.

Final persisted Mock: **2 courses / 2 sessions / 8 expected, executed and completed turns; 0 failed/missing;
16 Mock requests, 32 ledger events, 0 reviewer calls**. Independently matched each request SHA to its
reservation and all 32 PG records to full JSONL content. The original live run/policy, all 40 original PG
events, eight turns and two sessions also compare equal to the retained baseline export. **2,041 existing
tracked/raw files** retain their task-start hashes. The dedicated container is **exited 0**, volume retained.
No new real tokens or cost were generated by replaying historic usage into Mock envelopes.

All pre-existing tracked files and both original raw evidence trees are checked against the task-start
SHA inventory, excluding only Python bytecode caches. New artifacts are versioned separately. No original
result, score, source, dataset, identity or hash was overwritten. No CI/product default, other workspace,
push, PR, merge or deployment change occurred.

## Retest boundary and remaining blockers

The [retest plan](retest-plan.json) freezes the same original Python/spreadsheet 2 sessions / 8 turns,
including original turn-list and per-session data hashes; no budget-truncated scope or SQL fallback.
Run the read-only preparation command in README to reproduce chained identity/scope verification.
All changed conditions and new-paid-confirmation requirements are in README's retest checklist.

**Still unverified:** whether the moving `deepseek-flash` alias returns better facts, completeness or
citations under v11; whether its actual production response exposes model/cache metadata; actual token/cost
change and bill. Model alias/version drift and sampling nondeterminism confound a before/after comparison.
The old generic index query still has a retrieval miss; no universal retrieval or semantic grading fix is
claimed. A human should clarify the noted ordinal/dtype rubric ambiguities in a separately versioned future
dataset, without rewriting this baseline. These cases informed tuning and cannot establish generalization.
Derived passages change citation-ID granularity. A retest must compare task completeness and semantic
support/claim coverage against original source lines, not use fewer IDs or a changed pair denominator as
evidence of better teaching. All eight scheduled turns, refusals, failures and missing results remain visible.

No new paid authorization exists. Future same-scope real retest requires a freshly approved numeric USD
amount, 40-request maximum including failures/repairs, current pricing compatibility and acceptance of the
moving alias/local ledger versus supplier bill limitation. Reviewer off, concurrency one and retries zero
remain. First failure, unknown accounting or cap exhaustion stops the trial without top-up or auto-resume.

**NOT_RUN:** post-fix real task quality, real cost changes, actual invoice/account balance, independent human
agreement/kappa, real reviewer, SQL candidate evaluation, expanded 60/320-turn evaluation and learning effects.

Delivery adds only this report and `VERIFICATION.json` after final code verification at `862abe9`.
Reproducible raw outputs: `replay-final/audit.json`, `mock8/`, `targeted.xml`, `final.xml`,
`independent-recount.json`, `baseline-recheck.json`, `verification-final.json` and `artifact-manifest.json`
under `.data/tutor-repair-v1-20261107/`; associated bounded supervisor records are listed in VERIFICATION.json.
