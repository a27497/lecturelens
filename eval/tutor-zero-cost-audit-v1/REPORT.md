# Tutor and evaluation audit: zero-cost investigation

The immediate blockers are unreliable task-obligation measurement and repeated
failure to deliver bounded answers. Recommend **Batch 1: acceptance-contract
repair and bounded-delivery design/implementation**, in that order, with a new
explicit development identity after approval. Do not expand, tune on SQL, or infer
that changing citation representation alone fixes either problem. No repair is
implemented in this audit.

Audited checkout: `/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens`, clean
starting HEAD `7db24be3e820039fcc5d2f605ebfd6de76a9c724`. This batch adds only this
audit, independent diagnostics and tests. Product code, default identity, schemas,
frontend protocol, CI, frozen evaluations, references and historical results are
unchanged. Findings describe that starting product version. Final delivery SHA is
the local commit containing this report; exact diagnostic hashes and check results
are in [VERIFICATION.json](VERIFICATION.json).

**Real model / embedding / reviewer requests: 0 / 0 / 0; new provider cost US$0.**
Prior authorizations are expired. Real quality improvement, cost optimization,
independent human agreement, SQL holdout, scaling and learning effects are all
**NOT_RUN**. This is a Codex nonblind source/code audit, not an independent human
annotation study or a new model experiment.

## Evidence and reproduction

The current v14 product/evaluation sources and frozen bundle have no tracked
changes relative to actual v14 execution SHA
`81020d1abd7c89a995bf9eba153302af7481c71b`. The candidate chain and actual entries
verify. Reports were used as indexes, then checked against retained wire bodies,
parsed proposals, checkpoint state, published answers, original Markdown and
annotations. Reconstructed HTTP envelopes are **not original response bytes**.

| Historical run | Actual execution SHA | Exact request bodies replayed | Completed / failed / skipped / missing | Correct / scheduled; correct / completed | PG/JSONL events in new isolated replay |
| --- | --- | ---: | --- | --- | ---: |
| v12 original16 | `8358595c792b5ce28f965a5c724a0dc6d8b076bd` | 42 | 16 / 0 / 0 / 0 | 13/16; 13/16 | 84 |
| v13 corrected entry | `5bfca941e98f041d4efdcc6dcfb9f5d766d46554` | 34 | 12 / 1 / 3 / 0 | 11/16; 11/12 | 68 |
| v14 frozen16 | `81020d1abd7c89a995bf9eba153302af7481c71b` | 32 | 10 / 2 / 4 / 0 | 9/16; 9/10 | 64 |

All 108 request bodies match byte-for-byte. All 48 scheduled outcome records,
published texts/evaluations, failure/skip roots, checkpoint contents and runtime
reservations match. No successful answer replaces a failure. Replay exercises
the original v12 entry, repaired v13 entry, and v14 entry with injected
`httpx.MockTransport`; it does not replay model reasoning or an immutable supplier
backend. The 216 new PG events equal their new JSONL contents. Historical PG is
not opened or modified: historical exported snapshots/manifests are retained.

All **2,053 files** in five historical manifests verify unchanged: v12 real72,
v13 resumed487, v14 offline1,028, v14 live358, v14 diagnosis108. Original annotation
anchors/source bindings independently recount **84/45/47 assertions**, **74/37/42
citation-requiring assertions**, and **62/38/36 explicit pairs**, with
**59/37/36 supported labels**. The 77/44/45 source quotations are literal matches
in the original development materials. These checks verify provenance and
arithmetic; semantic labels still require judgment.

Historical local ledgers reconcile to provider core usage and wire hashes:
57,713,400 /45,606,300 /46,152,000 nano-USD for v12/v13/v14. These are historical
peak/no-cache estimates. Replayed charges are simulated retained usage, not new
costs. Supplier invoices and immutable backend identities remain UNKNOWN.

Reports additionally inspected: P8 v1–v9 history; first public v10 pilot; v11
same-scope retest and fresh16 failure; v12 entry/recovery; v13 locator/preflight
failure and correction; v14 offline, initial rejected preparation, asset recovery,
live trial and delivery diagnosis. Raw independent replay here is limited to the
three runs above. `.data/p8-tutor/` is absent in this checkout; old P8 PASS claims
cannot be independently recertified here. No other workspace/private account
directory was searched to fill that gap.

## Prioritized issue register

Priority expresses impact and dependency, not implementation convenience.
P0 blocks a credible next acceptance claim or complete delivery. P1 affects
source fidelity, answer validity or usable recovery. P2 is a bounded capability
or accounting limitation. Confirmed mechanism behavior is distinguished below
from unmeasured model outcomes.

### A01 — P0: question/reference obligations do not fully align

**Confirmed evaluation defect; reproduced; high confidence.**

- Evidence: `eval/tutor-v14-fresh-v1/questions.json`, dialogue
  `v14-sheets-lineends`, turn2; original spreadsheet lines76–78; historical
  `v14-frozen16-once/wire/029-request.json`; published turn2; new
  `complete/question-reference-gap.json`.
- Trigger: answer both explicitly requested platform/parser-condition questions
  without the reference's additional specific Excel-reopening example.
- Impact: strict frozen correctness is reduced for an obligation not explicitly
  requested. The source was retrieved, included and cited; this is not evidence
  of failed retrieval, lost source identity or inability to handle the stated
  question. There are315 unused characters, so length pressure is not established.
- Root: authoring/review did not enforce learner-question to mandatory-reference
  traceability. Similar ambiguity was already disclosed for old patient ordinal
  labels and dtype specificity in the first public pilot.
- Scope: add a new evaluation version with an explicit obligation/alternative
  matrix and independently checked references **before** candidate outcomes.
  Preserve old questions, labels and strict9/16 result. Do not relabel turn2 as
  correct in the frozen trial or insert the private reference into a model prompt.
- Related: A02, A10; historical duplicate counting H04. P0 because acceptance must
  measure intended obligations before judging a fix. Even a hypothetical alternate
  turn2 judgment cannot repair v14's all-complete/delivery gates.

### A02 — P0: bounded format repair repeatedly fails delivery

**Confirmed delivery defect; exact PostgreSQL replay; high confidence in mechanism,
unverified model-internal cause.**

- Evidence: v13 `new-sheets-qc:1`, wire033/034,1,657→1,691 characters;
  v14 `v14-sheets-portability:1`, wire024/025,1,982→1,799; and
  `v14-sheets-lineends:3`, wire031/032,1,818→1,633.
  `tutor/runtime.py:398–437`, `draft_repair_runtime.py:23–49`;
  `complete/{v13,v14}-replay-check.json`.
- Trigger: second proposal still exceeds text1,600 after the one permitted format
  repair. v14 evaluations are empty; no excessive distinct IDs are involved.
- Impact: v14 loses two answers and four later positions; v13 loses one answer
  and three later positions. These are three root failures, not ten independent
  model-semantic errors. No rejected draft is published or credited.
- Root: bounded delivery delegates exact length compliance to the same model.
  The v14 draft, kept sources, history and instructions are present, with turn
  reservations39,463/48,534 below64,000. Output usages647/697 are below1,200.
  Neither token exhaustion nor a missing-draft defect explains those two failures.
  The historical v13 missing-input defect is separately tracked as H01; matching
  terminal codes do not establish a shared model-internal cause across versions.
- Canonical citation markers consume594/660 characters in the repaired v14
  answers (9/10 occurrences,4/3 distinct IDs). This is material representation
  overhead, not proof a short-reference change is necessary or sufficient.
  Existing human feasibility samples fit with full IDs; they receive no score.
- Scope: after A01, define a new candidate's deliverable contract and compare
  bounded representations/content organization against retained multi-part tasks.
  Preserve supported points, conditions, every local support relationship and
  rejection fences. Never truncate a model answer or silently delete citations.
  Any protocol change needs its own explicit reviewed interface and identity.
- Related: A03/A04/A07. P0 because delivered learning conversations are missing
  even with healthy transport/accounting. The earlier short-citation proposal was
  read as historical context only; no prototype, alias transformation or candidate
  implementing it is executed in this audit.

### A03 — P1: valid citation identity does not establish a valid answer or evaluation

**Confirmed semantic enforcement gap and historical answer defects; Mock-reproduced;
high confidence in boundary, future real frequency NOT_RUN.**

- Evidence: `tutor/runtime.py:390–465`; v12 `fresh-python-tail:1` false whole-unit
  absence; v13 `new-sheets-validation:3` unsupported “only” converse; v13
  unpublished QC repair's exclusive sorting claim; new
  `complete/unsupported-publication.json`.
- Trigger: attach an authorized observed ID to an unsupported statement, or attach
  one valid citation anywhere while leaving evaluation uncited.
- Impact: course-scope assertions, learner feedback and pedagogical behavior can
  be wrong despite mechanically valid citations. The synthetic influenza/mastery
  fixture deliberately publishes; it is never a quality pass.
- Root: validation enforces ID membership, authority, size/outcome and punctuation,
  not entailment, per-field support, answer coverage or whether a hint reveals the
  answer. A nonempty evaluation is only a presence requirement. This is partly an
  explicitly documented design limit, not a newly discovered ID corruption bug.
- Scope: a new candidate should define claim/field support and scope checks,
  grounded evaluation observations and bounded semantic failure/revision behavior.
  A generic paid reviewer is not automatically the answer; existing reviewer
  failure evidence and independent evaluation are prerequisites. Zero-cost bad/good
  fixtures must remain distinct from real-model validation.
- Related: A01/A02/A05/A08/A10/A12. P1 because observed unsupported content has already
  reached published answers; existing source-identity checks cannot repair it.

### A04 — P1: authoritative READ silently omits source suffixes

**Confirmed current Java boundary defect; JUnit/H2 + mocks reproduced; high confidence.
Real Tutor quality impact NOT_RUN.**

- Evidence: `StudyEvidenceAuthority.java:78–81,115`; new
  `TutorEvidenceAuditTest.authoritativeReadSilentlyReturnsOnlyPrefixWithoutTruncationMetadata`.
- Trigger: normalized authoritative text exceeds1,200 Java UTF-16 units and a
  condition, correction or answer lies in its suffix. READ returns only the
  prefix and the same evidence ID, without truncation/range/continuation metadata.
- Impact: repeated READ cannot recover the missing tail; a model cannot distinguish
  a complete source from a prefix. This also prevents treating full-source public
  snapshot results as product-boundary acceptance. Current eval READ does not use
  this truncation.
- Root/scope: length bounding is performed at serialization without an observable
  completeness contract. Preserve bounded Java authority, but expose/consume
  recoverable source ranges or prepare bounded complete units. Define the Python
  observation behavior and new interface tests before implementation; no DB-schema
  change is established as necessary.
- Related: A02/A03/A05/A09. P1 because required evidence can disappear before model
  choice, and no amount of same-ID rereading recovers it.

### A05 — P1: evidence normalization destroys programming structure

**Confirmed source transformation; JUnit reproduced; high confidence.**

- Evidence: `CourseEvidenceService.java:124,142`; authority returns
  `normalizedText`; new normalization test in `TutorEvidenceAuditTest`.
- Trigger: source code or instructional layout uses meaningful line breaks and
  indentation. Actual normalization changes
  `for value in names:\n    length += 1\nprint(length)` into
  `for value in names: length += 1 print(length)`.
- Impact: loop boundary/code syntax disappears in the model-facing product source,
  while public Markdown evaluations preserve it. This is a separate root from
  prefix truncation and from Python's Mock rewriting.
- Scope: preserve raw/structured pedagogical text at the tool boundary while
  retaining normalization for retrieval where useful; assess other consumers of
  this shared Java service before changing it. Evidence identity and content
  provenance must remain explicit.
- Related: A04/A06/A09. P1 because the course's taught semantics can be altered
  before generation. No production/student source was used to demonstrate it.

### A06 — P1: product Mock corrupts valid indexing despite opt-in candidate repair

**Confirmed default-path defect; offline Mock reproduction; high confidence.**

- Evidence: `tutor/runtime.py:27–44,85–96`, `tutor/app.py:41–47`, and
  `tutor/python_runtime.py:10–49`; diagnostic `test_default_mock_corrupts_python_indexing`.
- Trigger: a source contains `values[0]` or a slice/list and the product factory
  installs the base `TutorRuntime`/`MockTutor`.
- Impact: `MockTutor.decide()` changes source square brackets to parentheses,
  yielding `values(0)` in the answer while citing the original source. Its base
  system prompt also demands parentheses for indexing. The displayed example may
  be wrong even though the opt-in v10–v14 real-evaluation prompts preserve syntax.
- Root/scope: source syntax is conflated with citation delimiters in the default
  path. Reconcile the default demo's source-preservation contract independently
  of the explicit evaluated variants; do not silently switch default identities.
- Related: A03/A05; H02 is fixed **only in the opt-in path**. P1 because the
  deterministic default itself corrupts instructional content; no model error is
  needed. This audit makes no default or prompt change.

### A07 — P1: lost submit response plus exhausted session traps frontend recovery

**Confirmed UI state defect; mounted Vue component reproduced; high confidence.**

- Evidence: `CourseTutorPanel.vue:21–23,41–45,74–99,129,149–154`; new
  `frontend/tests/diagnostics/tutorZeroCostAudit.test.ts` first case.
- Trigger: TURN succeeds but its HTTP response is lost; GET later returns that
  completed client ID and `model_calls==max_calls` (or40 submitted turns).
- Impact: GET displays the answer but does not reconcile `pending`. Exhaustion
  disables the same-ID retry; `pending` disables new conversation, session switch
  and editor. Reloading/remounting escapes, but the provided recovery controls do
  not. Duplicate requests are not observed.
- Root/scope: read-side reconciliation does not clear a confirmed pending client
  ID, while exhaustion guards also block the idempotent read/replay route.
  Fix the frontend state transition with exact ID/text/mode reconciliation and
  tests for completed/failed/cancelled/conflicting/absent pending turns.
- Related: A02/A08. P1 because loss of a transport acknowledgment can make an
  otherwise persisted session unusable. No real browser/account was used.

### A08 — P2: long-session summary drops old feedback and answer tails

**Confirmed information loss; PG reproduced; documented bounded-context tradeoff.
Wrong downstream model decisions NOT_RUN.**

- Evidence: `tutor/runtime.py:183–203`; `complete/long-context-loss.json`.
- Trigger: a completed turn moves outside the recent-six window. Summary keeps
  only first220 characters each of learner text and answer; evaluation is omitted;
  whole summary is sliced to last2,000 characters.
- Impact: a correction only in evaluation or answer suffix is unavailable to turn9
  in the fixture. Actual v12–v14 sessions are≤5 turns and do not exercise this.
- Root/scope: prefix extraction is not a semantic learning-state representation.
  Define which learner facts/corrections must persist within a bounded session,
  with provenance and uncertainty; keep future memory out of this batch. Model
  quality testing is separate from proving text survival.
- Related: A03/A07/A11. P2 here because loss is established but observed wrong
  long-session tutoring is not; do not claim the rolling summary preserves all
  learner corrections.

### A09 — P2: deterministic retrieval returns arbitrary sources for zero overlap

**Confirmed evaluation-path limitation; three offline queries reproduced.**

- Evidence: `lecturelens_real_eval/runner.py:85–90` and
  `test_zero_overlap_search_still_returns_eight_sources`.
- Trigger: a Chinese query, punctuation-only query or unmatched English word has
  no `[a-z]{3,}` token overlap. Stable sorting still returns the first eight rows.
- Impact: there is no retrieval no-hit observation or relevance score; the model
  must infer insufficiency from arbitrary excerpts. This path cannot measure
  Chinese-course retrieval, deployed dense retrieval or a reliable scope boundary.
- Root/scope: fixed lexical top-eight policy. If retrieval quality becomes the
  learner-flow dependency, design explicit no-hit/ranking observations and a
  product-shaped offline authority fixture; retain old snapshot behavior for
  historical replay. This is not evidence real embeddings are broken.
- Related: A03/A04/A05. P2 because the known English development conclusions are
  already narrow; wider claims would be invalid without a new evaluation path.

### A10 — P2: supplied-source fidelity can disagree with executable truth

**Confirmed source limitation and intentional historical scoring policy.**

- Evidence: v14 spreadsheet source lines92–94 says `2\\r` is not a valid integer;
  local Python `int("2\r") == 2`; `complete/source-truth-limitation.json`.
  R and external importers were not run.
- Trigger: treating the historical lesson's attributed example as a universal
  Python parsing fact instead of the described incompatible-parser scenario.
- Impact: source-supported answers alone cannot prove current technical correctness
  or educational value. Other source caveats were already disclosed for shape
  wording, null/mean propagation and field-name digits in the public content review.
- Root/scope: outdated/overbroad teaching source versus closed-source evaluation
  policy. Historical sheets explicitly score attribution/conditional handling;
  no frozen grade is changed. Future tasks must distinguish “what the lesson
  states” from “what this executable example proves,” without silently correcting
  private gold after seeing outcomes.
- Related: A01/A03/A09. P2 because the frozen source-attribution boundary is
  disclosed, but broader correctness claims would be unsupported.

### A11 — P2: cancellation can drop known usage from the Tutor turn

**Confirmed turn-telemetry defect; PG + deterministic cancellation reproduced.**

- Evidence: `tutor/runtime.py:330–340`; `complete/cancelled-usage-loss.json`.
- Trigger: cancellation commits while a provider call is in flight, then that call
  returns known usage. `guard()` raises before checkpoint/usage persistence.
- Impact: turn has `model_calls=1` and nonzero reservation but `usage=[]` in the
  fixture. Late answers remain unpublished. The paid eval ledger settles inside
  Channel before return, so this does **not** demonstrate missing billed charges
  in the separate eval ledger.
- Root/scope: publication cancellation fence also gates bookkeeping. Preserve the
  no-publication/no-resend invariant while retaining safe completed-call usage
  independently. Add cancellation/deadline/shutdown and ledger-versus-turn tests.
- Related: A07/A08. P2 because authority and budget safety remain intact; runtime
  per-turn usage is incomplete on this race.

### A12 — P2: Socratic acceptance tests the label/question mark, not answer withholding

**Confirmed pedagogical enforcement gap; Mock/PG reproduced; real quality NOT_RUN.**

- Evidence: `tutor/runtime.py:448–460`; `complete/socratic-surface-only.json`.
  Existing `test_socratic_full_answer_is_protocol_failure` actually changes the
  outcome to `answered`; its name does not establish full-solution detection.
- Trigger: return the complete polynomial solution/result with
  `outcome=socratic_prompt` and append “Understood?”. The new fixture publishes.
- Impact: a completed Socratic protocol is not evidence the learner received a
  guiding question rather than an answer. v12–v14 development tasks all disable
  Socratic mode, so their metrics do not cover this behavior.
- Root/scope: pedagogical compliance is represented by an outcome enum and
  punctuation. Define grounded hint versus full-answer acceptance separately,
  with learner-reply feedback examples and independent semantic evaluation.
  This is distinct from factual entailment in A03 and does not require a new tool
  or paid reviewer merely to reproduce.
- Related: A03/A08. P2 because the boundary is proven but no new real Socratic
  performance measurement is available.

## Risks, tradeoffs and historical fixes

| ID / class | Evidence and conclusion | Next disposition |
| --- | --- | --- |
| R01 — unverified semantic risk | JSON user data labels evidence/history/rejected drafts untrusted, and tools are allowlisted. There is no real adversarial prompt-injection quality trial here. HTML is escaped in Vue; no arbitrary execution tool exists in this Tutor. | Model resistance and adversarial multilingual source behavior **NOT_RUN**; do not claim prompt wording is a proven semantic boundary. Related A03. |
| R02 — enforcement limit | `safe_exec.py` clears environment and asserts the Python socket audit hook; fixtures reject key lookups and real HTTP transports. Native libpq and non-Python children are outside those counters. | No external bypass attempted. This is a Python/process convention, not OS-wide isolation. Consider a separate kernel egress fence for future execution if it becomes a concrete dependency; no CI/platform expansion in this audit. |
| R03 — evidence availability | `.data/p8-tutor/` is absent; old v8/v9 real PASS rows in `eval/p8-tutor/REPORT.md` lack their local raw records here. v10/early-v11 raw records are present but were not fully replayed this batch. | Early P8 PASS provenance/labels **NOT_CHECKED**, old model version/metadata gaps stay UNKNOWN. Do not inherit them as current Tutor acceptance. |
| D01 — failure policy | v12 protocol closes a failed conversation, including later same-session independent topics, and continues later sessions; v14 actually exercises independent-session continuation. | Intentional conservative stop policy. Preserve scheduled/observed denominators; no invented antecedents, no automatic retry. Four v14 skips are not four extra semantic failures. |
| D02 — accounting units | Runtime reserves message/schema UTF-8 bytes+1,200; ledger reserves actual wire bytes at fixed rates plus output allowance; settlement uses reported core tokens. Cached/weekend public-rate estimate is a separate quantity. | Conservative proxies are not token counts or supplier billing caps. Usage exceeding reservation blocks later sends; immutable alias/backend and invoices remain UNKNOWN. Cost optimization **NOT_RUN**. |
| D03 — output surface | HTTP response bodies are read in chunks inside Channel, but answers are published only after full proposal validation and atomic DB commit; Vue polls GET. It is not incremental token publication. | No observed pre-validation draft exposure or canonical ID rebinding in the audited path. Source timestamps0/0 in public Markdown eval are placeholders, not valid browser seek acceptance. Real browser/media navigation **NOT_RUN**. |
| D04 — annotation sensitivity | v13 direct33/37 versus frozen36/37; v14 direct35/42 versus frozen42/42 uses signaled bounded derivations. Full-turn v14 coverage remains7/12. Annotation granularity is nonblind judgment. | Keep direct and frozen metrics side-by-side; no new success numerator or human agreement. Related A01. |
| H01 — fixed in v14 opt-in | v13 repair request034 omits rejected draft; v14 wire025/032 and exact replays include it intact. | Do not reimplement the missing-draft fix or claim it solved length compliance. Related A02. |
| H02 — fixed in opt-in v10+ | Python-specific prompt preserves language brackets and parser keeps ordinary indexing; current product Mock/base prompt differ (A06). | Preserve variant distinction; no default switch. |
| H03 — fixed in current mechanism | Earlier search results remain in the per-turn union (≤16); READ batches≤8; restart restores received response without retransmission; unknown reserved outcomes fail closed. | Current inherited PG regressions exercise union, owner/version/deletion, idempotency, cancellation, budgets and recovery. No new defect found in these exercised boundaries; concurrency outside those fixtures remains **NOT_CHECKED**. |
| H04 — corrected historical annotation | v12 original requiring denominator74 double-counts markers5 c5/c4; additive v13 cause audit reports73, supported59/73 and full turns4/12 instead of3/12. Original task13/16 and FAIL stay unchanged. | Preserve original plus explicit supplement. Do not compare old74 with new derivation metrics as a causal improvement. |
| H05 — fixed preflight/formatting defects | v13 v2 corrects source locators; overlay adds missing pytest import. v14 restored source hash59ad81…ffc53; Ruff exclusions protect eval and .data including explicit-file invocation. | Current actual entries verify; regression uses disposable mirrors. No directory formatting or source-hash relaxation here. |
| H06 — historical metadata gap | First public trial failed to capture returned-model/cache fields; later DecodedMetadataTransport captures allowlisted decoded telemetry. All108 v12–v14 histories preserve actual local call IDs/usage. | Old missing metadata cannot be reconstructed as original fact. Full raw response/header bytes remain unavailable even in v14. |

## Coverage and explicit limits

| Requested area | Checked in this audit | Remaining boundary |
| --- | --- | --- |
| Evaluation trust | Actual v12/v13/v14 entries, identity chain, source/quote bindings, question/reference gap, all scheduled outcomes, arithmetic, direct/frozen support, dev-only loader and reference exclusion in all108 wires | Independent gold labels/human agreement **NOT_RUN**; full early P8 raw review **NOT_CHECKED**; SQL question/reference content and output quality **NOT_RUN** |
| Retrieval/context | Question/Solution source-only grouping, member IDs/hashes, stable lexical ranking/no-hit behavior, exact108 histories, kept repair view, 6-turn/2,000-char summary, Java normalization/truncation | Real embeddings/ingestion/ASR/video, Chinese or long-course relevance **NOT_RUN**; arbitrary malformed source structure and all two-search ranking combinations **NOT_CHECKED** |
| Generation/repair | Exact settings/tool schemas/requests, source presence, length/character/token units, rejected draft, one-shot behavior, scope additions, required points, answer/evaluation/Socratic negative fixtures | New real-model compliance/semantic repair/quality gain **NOT_RUN**; hidden reasoning is unavailable |
| Citations/output | Canonical observed ID→READ binding, complete-turn atomic publication, current mapping/persistence/recovery, rejected draft visibility, escaped Vue rendering, polling display and known UI recovery race | Real browser/media seek **NOT_RUN**; any short-reference implementation/prototype **NOT_RUN**; malformed markup variants beyond current tests **NOT_CHECKED** |
| Session reliability | PG mechanisms for state, idempotency, version/tombstone, cancellation, reserved/received recovery, persistent caps; all local-failure/dependency roots reproduced; long-context loss and late usage | New real-provider cancellation/restart, multi-worker stress, deployment transport timing **NOT_RUN/NOT_CHECKED** as applicable |
| Entry/protection | Current source integrity, frozen rejection/format mirrors, no-egress preflight, caps, unknown usage/failure stops, exact original wire/usage/ledger reconciliation, separate disposable DB | OS-wide network isolation **NOT_CHECKED**; supplier invoice/backend identity UNKNOWN; new real request counts always0 |

No evidence establishes unseen-course generalization, automatic grading, learner
mastery, long-term memory, scheduling, human agreement, cost reduction or learning
effects. Model-selected tools and mechanics are implemented; these are separate
from measured tutoring outcomes. The real product remains opt-in Mock and is not
silently promoted to the v14 evaluation identity.

## Proposed repair sequence — not executed

Estimates are engineering days for this codebase, not delivery promises. Each
batch needs approval before it is implemented. All offline work below can cost
US$0; any real model/embedding/reviewer evaluation needs a separate new paid grant.

| Batch | Goal and scope | Acceptance | Dependencies | Estimate / paid work |
| --- | --- | --- | --- | --- |
| **1 — recommended first** | A01: new development obligation/reference/rubric version with explicit alternatives and source-truth policy. Then A02: select and implement a bounded-delivery candidate based on retained failure evidence; preserve content/support and canonical authority. Separate content organization, repair observation and serialization alternatives; short display references remain one unselected option. | Every mandatory point maps to the learner request; preserved old scores/identities; exact108 historical replay still fails where it failed; independent multi-point fixtures retain all required facts and local support, reject overlength/foreign/stale IDs, survive restart and preserve failed/skip census. No output-contract change sneaks into defaults. | A01 precedes interpreting delivery/quality gains. Authority and idempotency invariants remain prerequisites. | **3–5 days**, offline US$0. Real delivery/quality gain stays **NOT_RUN** pending a later approved trial. |
| 2 — product evidence fidelity | A04/A05/A06: bounded but recoverable source text, meaningful code structure, explicit default Mock preservation. Do not inherit public-snapshot quality into this path. | Java→Python contract fixtures for suffix conditions, indentation, Unicode boundaries, version/deletion/ownership and citations; bounded continuation/stop behavior; correct default Mock examples; no shared-consumer regression. | Batch1's obligations and candidate/output contract. These are separate roots with separate tests even if shipped together. | **2–4 days**, offline US$0; optional later provider validation separately authorized. |
| 3 — semantic learning behavior | A03/A08/A09/A10/A12: supported answer/evaluation observations, scope/direction, bounded learner correction context and useful retrieval no-hit observations. Keep Socratic/full-answer quality distinct from punctuation. | Independent good/bad/incomplete/conditional fixtures; evidence provenance and budget stops; prior correction remains observable when required. Freeze new development tasks before results; preserve negative trials. | Batches1/2 give valid acceptance and faithful evidence. Reviewer addition is a design decision, not automatic approval to call one. | **3–6 days**, offline US$0. Real semantic quality/pedagogy remains **NOT_RUN** without new authorization and fresh independent evaluation. |
| 4 — recovery and telemetry | A07 frontend pending reconciliation; A11 late usage bookkeeping, preserving cancellation and no resend. | Lost acknowledgment at40 turns/60 calls; same-ID replay; refresh/cancel races; failed/cancelled/absent/conflicting pending states; late usage retained without late answer publication; ledger reconciliation. | Known fixes can be designed independently, but output/evidence contracts from preceding batches must remain stable. | **1–2 days**, offline US$0. No real account/browser or model needed for mechanism acceptance. |
| 5 — evaluation beyond this boundary | Obtain accessible early historical evidence if needed; independent fresh holdout and human agreement only under a new scope. Scaling/cost tuning/learning study follow demonstrated correctness and delivery. | Independent dataset/version split, full scheduled denominators, preserved failures, comparable workload costs and explicit uncertainty. No reuse of consumed dev data as a holdout. | Earlier batches accepted; explicit new data/payment authorization. Existing SQL is not tuning material. | Scope-dependent; **not authorized, NOT_RUN**. |

## Verification execution and cleanup

The audit has a dedicated newly created PG17 container
`lecturelens-tutor-audit-20261108`, using an already local pinned image
`cf134a767f47`, loopback25841,384MiB/0.5CPU and tmpfs data. No existing dedicated
evaluation volume or running service is used. Every Python fixture creates and
drops a unique schema. Java uses H2/Mockito; Vue uses mocked API calls. Maven runs
with `-o`, and no package/model download is performed.

Commands and terminal records are under
`.data/tutor-audit-20261108/checks/`. Main commands:

```sh
python3 scripts/dev/run_check.py --name audit-final --timeout 1200 --output .data/tutor-audit-20261108/checks -- agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-audit-20261108/network-delivery scripts/dev/check_tutor_zero_cost_audit.py --output .data/tutor-audit-20261108/delivery
python3 scripts/dev/run_check.py --name audit-existing-mechanisms --timeout 1200 --output .data/tutor-audit-20261108/checks -- agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-audit-20261108/network-existing scripts/dev/check_v14_assets.py --output .data/tutor-audit-20261108/existing-mechanisms
python3 scripts/dev/run_check.py --name audit-java --timeout 240 --output .data/tutor-audit-20261108/checks -- mvn -o -f backend/pom.xml -Dtest=TutorEvidenceAuditTest,TutorControllerTest,StudyAuthorityTest test
python3 scripts/dev/run_check.py --name audit-frontend-corrected --timeout 120 --output .data/tutor-audit-20261108/checks -- /opt/node/bin/node frontend/node_modules/vitest/vitest.mjs run --root frontend --config vitest.config.ts tests/diagnostics/tutorZeroCostAudit.test.ts src/components/task-detail/CourseTutorPanel.test.ts --reporter=json --outputFile=/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens/.data/tutor-audit-20261108/frontend-results.json
```

Final checks: **25 new Python diagnostics**, **249 inherited Python mechanism/asset
checks**, **20 Java tests** (two new diagnostics), and **19 Vue tests** (two new
diagnostics), all passed, with zero failures/errors/skips. Python tests use actual
isolated PostgreSQL where required; DB checks are not skipped. The inherited
suite has three existing import/deprecation warnings. Java has existing Mockito
agent warnings. These counts do not measure model intelligence.

Exact command records, cleanup and manifest hashes are in
VERIFICATION.json. Tests that reproduce a defect assert current behavior; their
PASS means the defect was reproduced, never that it was repaired.

An initial new diagnostic assertion mistakenly treated the word “Excel” as absent
from lineends2; it actually occurs in the OSX discussion. That rehearsal is
preserved (19 passes/1 failure). The check now targets the missing reopening
example, preserving historical9/16 and the original answer. An initial frontend
launcher resolved `frontend/frontend/vitest.config.ts`; it failed before tests
and was corrected to the config relative to the explicit root. A subsequent
24-test diagnostic pass predates added quote/accounting assertions; the next
24-test run checks those too, and the final25 adds the default-Mock syntax
reproduction. An initial additive patch used an import Ruff had already removed
and was rejected without a file change. These are audit-authoring mistakes, not
model trials. Primary inspection artifacts use `complete/`; final25 repeats them
under `delivery/` and adds `delivery/default-syntax-loss.json`.

Only the audit-created container is stopped/removed after terminal checks and
schema cleanup, with original23 running container IDs compared. No source/frozen
formatter is run; Ruff touches only the two new named diagnostic Python files.
Private transcripts, generated test outputs and downloaded material stay ignored.
There is no push, PR, merge, deployment or server rental.

**Stop after this audit. No implementation or paid execution is authorized.**
