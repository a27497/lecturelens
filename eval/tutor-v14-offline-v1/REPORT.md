# v13 diagnosis and opt-in v14 offline repair

**Offline mechanics only; real repair efficacy NOT_RUN.** This stage made **zero
real model, embedding and reviewer requests**, costing **USD 0**. Historical v13
remains FAIL: **12 completed, one failed, three skipped, zero missing; 11/16
scheduled complete-correct and 11/12 conditional on completion**. There is no new
real quality score, no relabeled rejected draft, and no continuation of old paid
authorization.

Started clean at `3dd6cd70d83d58c5cda7741d14f758f563065bc9`, branch
`codex/tutor-scale-preparation`, in the requested worktree. Historical execution
was `5bfca941e98f041d4efdcc6dcfb9f5d766d46554`. Final runtime/check code is
`bffe4ac2f96f43a5df645e5a40d88b49eaa498b8`; the delivery commit adds documentation
and non-sensitive verification only. Actual check commands/results and cleanup
are recorded in `VERIFICATION.json` and the private artifact directory below.

## Original evidence and diagnosis

Read AGENTS, the product contract, execution guide, frozen v12/v13 contracts and
v13 execution sheet before changing behavior. Original retained evidence is
`.data/tutor-v13-resumed-20261107/`; new evidence is exclusively
`.data/tutor-v14-offline-20261107/`. The audit recomputes all **487** hashes in the
old manifest (`bf07f62a2b0477c8c8d4f323379f542f7e656e2e4c9ebfc236ca0912ef574b26`),
checks original answer offsets/source quotes/citation bindings and independently
reconciles the old wire/usage/ledger records. It does not execute the old annotation
script or rewrite original judgments. This remains **Codex nonblind source review,
not independent human evaluation**.

`v13-new16-first/turns.jsonl`, position `new-sheets-qc:1`, and wire requests
032–034 establish the sequence:

1. Search returns the relevant original-formula/working-values/README passages.
2. The first finish is valid JSON/proposal with known usage and observed citation
   IDs, but **1,657 Unicode characters**. The model-facing schema already advertises
   maxLength 1,600; the normal prompt targets 1,200. This is generated content
   violating the existing output contract, not a JSON parse failure.
3. Publication validation records `TUTOR_FINISH_REPAIR_REQUIRED`, correct actual
   length and limits, kept IDs and one repair opportunity. Repair request 034
   contains four canonical kept sources with unchanged ID/text/location; the
   original eight-source union remains authorized. There is no evidence loss or
   rebinding relevant to these required points.
4. The next generated finish is **1,691 characters**, longer than the first.
   Validation correctly raises **TUTOR_FINISH_FORMAT_INVALID** after the single
   repair. No answer/citations are published; the full rejected response survives
   in the checkpoint. An output-token allowance is not a character-length guarantee.

The turn reserves **22,739 + 14,582 = 37,321 <64,000** proxy units. The global
ledger is healthy at **34/80 requests**, **USD 0.0456063/0.70**, pending 0 and blocked
null; every HTTP response succeeded with known usage. No call/fee/turn budget was
exhausted. Enlarging those limits would not fix this failure.

A **confirmed repair-context defect** is visible in request 034: it contains the
learner question, evidence and repair observation but **not the rejected draft**.
The runtime stores `state.response` durably, yet `request()` does not serialize it.
The stateless repair sees instructions to rewrite a draft that it cannot inspect,
so must regenerate from the task. The patch restores that missing input. The
evidence does **not** establish that this omission alone caused the model to grow
the answer, or that restoring it will make a real model comply; that causal and
quality claim remains unverified. Both drafts already contain the requested
points plus redundant/optional material. No particular deletion is treated as a
proven solution.

Under the unchanged `v12-session-isolated-live-v1` protocol this exact terminal
code is local: the session closes, turns2–4 are **SKIPPED**, all rooted at
`new-sheets-qc:1`. Turn2 depends on1, turn3 on2, turn4 on2/3. No fabricated
conversation is substituted. It is the last session, so real independent-session
continuation was not exercised; the separate full16 Mock faults exercise it.

## Exclusive assertions checked against original source

| Output | Original spreadsheet unit | Finding |
| --- | --- | --- |
| Published `new-sheets-validation:3`, claim c6: “only the list form produces the drop-down aid” | `materials/carpentries-spreadsheets-new.md` in the v13 bundle, lines81–85: **if** a list of options restricts entry, a dropdown is provided | The converse/exclusivity is not established. The observed citation `0dc6add…dc18af` supplies the conditional, not exclusivity. The requested list/bounds explanation is otherwise supported. Retain the original uncertain whole-answer judgment and unsupported pair. |
| Unpublished repaired `new-sheets-qc:1`: “sorting is only safe for a well-structured dataset that does not contain formulas” | Same source lines109–111: **if** well structured and formula-free, sorting should not affect integrity; expand whole rows to avoid corruption | A sufficient condition becomes a necessary/exclusive one. Present in the original repair proposal/checkpoint, excluded from published-answer metrics. |

Both relevant excerpts reached the model, and the added clauses were in its
generated text, before parsing/publication. These are unsupported inference/scope
additions, not demonstrated retrieval misses, citation-ID corruption or proof of
false behavior in all spreadsheet software. We do not use outside software facts
to retroactively pass them. No old whole-answer label changes are warranted.
The Python stride answer's “does not itself discuss multiplication” is scoped to
the cited step passage/elementwise comparison; the full unit separately teaches
list repetition. This contextual reading is retained explicitly, not converted
into an assurance of whole-unit absence or independent reviewer agreement.

## Minimal behavior change

New explicit development identity: **p8-tutor-draft-repair-v14-development**,
manifest SHA-256 **180929dee65677f105b1d9c85705394b28b8dc90a0edef2e99abc140821420b3**.
`v14_contract.verify_candidate()` checks the unchanged parent and new runtime
hashes; `verify_offline()` also pins this audit and collected tests. No product
default/Java/CI/old identity or frozen asset is edited.

`DraftRepairTutorRuntime` inherits v13 and changes only request construction:

- At format repair, copy the durable rejected finish's outcome/text/evaluation
  into **untrusted** `rejected_finish` data. It is neither evidence nor authority;
  full draft content is retained without slicing. Missing/malformed draft fails
  closed with a protocol error. Existing source re-READ and v12 kept-source view
  run first; removed IDs are not reauthorized by appearing in the draft.
- Add concise guidance to edit that draft, preserve all supported requested
  points/citations, count citation IDs in the existing character limit, and avoid
  new claims during format repair. Add one source-condition direction rule:
  `if A then B` does not entail `B only if A`. There are no course answers,
  reference points, lesson names or question-specific exceptions in product code.
- Reserve the **actual complete new request** including draft, schemas and existing
  output allowance. Larger context can still fail the original budget; it is not
  truncated or granted extra capacity.

Text 1,600/evaluation 500, four distinct IDs, 1,200 output tokens, search/repair/call/
session limits and failure classification are unchanged. The prompt adjustment
is a grounded behavioral mitigation, **not a semantic entailment verifier**.
An observed-ID unsupported sentence can still publish: the tests preserve and
explicitly expose that limitation. No lexical ban on “only,” post-hoc citation
attachment, draft rewriting, scoring relaxation or automatic second repair is
introduced.

## Historical citation denominator supplement

All12 published answers (nine substantive, three clean refusals) were reviewed.
The inventory contains **45 distinct assertions**, **37 requiring positive source
support**, and **38 explicit substantive claim–citation pairs**. Semantic repeats
are deduplicated; named code/output/list examples may bind their opening/closing
citations. Arbitrary nearby paragraphs do not inherit a citation. Negative scope,
conversation and refusal statements are truth-reviewed without inventing positive
citations; their explicit substantive pairs still count.

| Metric | Numerator / denominator | Result |
| --- | --- | --- |
| Explicit pair support | 37 supported /38 reviewed pairs; one unsupported, zero uncertain | 97.37% |
| Direct citation presence | 34 requiring assertions with explicit attachment /37 | 91.89% |
| Directly supported requiring assertions | 33 /37 | 89.19% |
| Frozen-rubric supported coverage | 36 /37, including three signaled bounded derivations | 97.30% |
| Fully supported expected answers | 8 /12 scheduled answerable positions | 66.67% |
| Direct-only full-answer sensitivity | 5 /12 scheduled answerable positions | 41.67% |

The three non-inline derivations are sharing:3 c4 (array + index order + zero-based
premises imply peppers), stride:1 c5 (explicit own arithmetic from cited values),
stride:2 c2 (third entry/index2 from zero-based and displayed list). Each local
premise is identified and source-checked in `final-cases/historical-audit.json`.
They add coverage credit under the **pre-existing** bounded-derivation rule, not
invented explicit citation pairs. Direct-only numbers expose the stricter reading.

The unsupported published exclusive claim is the only uncovered requiring
assertion. Fully covered turns are the six substantive Python answers and
validation1/2. Validation3 is incomplete in support; the three other answerable
positions failed/skipped. Failed and skipped positions contain no published
claim inventory, so cannot meaningfully enter pair denominators, but remain in
**16 scheduled /12 completed /12 scorable /12 scored**, whole-answer **11/16**,
conditional **11/12**, and expected-answer coverage **8/12**. Refusals remain
**3/4 scheduled, 3/3 observed**; contextual consistency **7/10 scheduled, 7/7
observed**. Nothing here changes the original gate FAIL.

## Historical cost reconciliation

The 34 real v13 requests include search/finish and rejected drafts/repair, with
zero transport retries, reviewer or embedding requests. Provider usage is input
**127,601**, output **6,105**, total **133,706**, cache hit **35,456**, miss **92,145**.
All 34 records have known usage/cache, unique local/response/ledger IDs and the
reported model `deepseek-flash`. Supplier request-header IDs and immutable version
remain unknown.

The retained official pricing HTML hashes to the cached November7 observation:
weekend off-peak USD 0.003/hit, 0.15/miss, 0.60/output per million. Consequently:

`(35456 × 0.003 + 92145 × 0.15 + 6105 × 0.60) / 1000000 = USD 0.017591118`.

This is a **rate-calculated usage estimate**, not a supplier invoice. The existing
conservative ledger settles with peak input-miss 0.30/output 1.20 without cache or
time discounts: **USD 0.0456063**. Before each send it reserves exact wire UTF-8
bytes×300 plus 1,200 maximum output tokens×1,200 nano-USD; it replaces that
reservation with known usage at settlement. Largest reserved-plus-settled prefix
is **USD 0.0492906**, ending pending 0. Every prefix, wire hash and settlement is
recomputed. These are different units/policies, not evidence of duplicate billing.
The supplier invoice, actual debit and provider-enforced hard cap are **UNKNOWN /
NOT QUERIED**. Cached rates are used only to audit history; no current bill,
account, credential or real endpoint was accessed this stage.

## Verification, limits and next step

Final collection and execution use the same code commit and explicit new/historical
test paths through `scripts/dev/run_check.py` and `eval/tutor-scale/safe_exec.py`.
The clean interpreter permits only isolated PG port25841, strips provider/proxy
environment, rejects credential lookups and real HTTP transport, and records
socket counters. Each database test owns a disposable schema. Replays reconstruct
HTTP envelopes from retained parsed proposals/usage: **not original raw response
body bytes and not a new model run**. Old control checks all 34 exact request bodies;
new replay preserves the same 12 answers, same failure and same three skips.

**Final result: 219 collected, 219 passed, zero failures/errors/skips**, including
33 new v14 checks, 46 frozen v12 entry checks, 18 v13 grounding checks and 122
existing Tutor checks. Supervisor exit0, 157.547s (pytest 155.77s). Three existing
test-loader/deprecation warnings are not skipped tests. Ruff and diff whitespace
checks pass. Python socket counters are all zero; libpq connections are outside
those counters, and actual PostgreSQL execution is established by schema/
transaction tests and scoped record reconciliation. Read-only comparison of the
old run's 68 events, 13 turns and 4 sessions exactly matches its retained snapshot.

Exact final supervised command (append `--collect-only` for the separate collection
check; use its separately recorded `v14-collection`/`network-collection` names):

```sh
python3 scripts/dev/run_check.py --name v14-final --timeout 1200 --output .data/tutor-v14-offline-20261107/checks -- agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-v14-offline-20261107/network-final .data/tutor-v14-offline-20261107/final_check.py
```

The guarded script invokes `pytest -q` on
`eval/tutor-v14-offline-v1/test_v14.py`,
`eval/tutor-v12-rerun-v1/test_run.py`,
`eval/tutor-v13-grounding-v1/test_grounding.py` and
`agent-service/tests/test_tutor.py`, with retained JUnit output and disposable
basetemp. Commands, logs, scripts and collection inventory are retained. The first
read-only historical PG audit used a UUID-array cast against text ID columns and
aborted; the corrected text-array audit passed. Both attempts are preserved and
neither wrote historical records. One test-authoring bracket error was corrected
before the final freeze; it is recorded rather than presented as a passed check.

The actual-failure v14 replay reserves **40,096 <64,000**, including the exact
1,657-character rejected draft, versus old 37,321. A test-only 691-character repair
preserves every required file/formula/README point with its supporting citations;
it verifies publication mechanics, not model compression ability. An initial
64,001-character injected draft instead exhausts repair reservation before a
third call, demonstrating the unchanged context cap.

Tests cover Unicode length−1/exact/+1 for both fields; valid initial/overlong
initial/overlong repair; actual failed initial plus an entirely test-only short
repair retaining all file/formula/README requirements and citations; unchanged
canonical evidence mapping; four/five citation handling; full draft budget
refusal; absent draft safety; ordinary/Socratic/multiturn historical behavior;
16-position Mock completion, local failure/dependency skip/independent session
isolation; unknown usage/auth/authority/global call and fee stops; complete PG/
JSONL accounting. Unsupported conditional converses are retained as semantic
negative fixtures rather than mislabeled passes. See exact results in
`VERIFICATION.json`.

Remaining risks: prompt adherence, real compression with full cited content,
source exclusivity reasoning and true cost impact are unmeasured. Adding a draft
uses context budget and can legitimately make repair capacity unavailable. There
is no independent entailment checker or human agreement measurement. The new
identity has an offline manifest, **no live entry frozen for new samples**.
An offline pass does not justify expansion or establish real quality improvement.

Only this stage's exact dedicated PG is started/stopped; its evidence volume is
retained and the 23 original running containers are left running. No production,
real student/manual account data, SQL holdout, other worktree, CI, push, PR, merge
or deployment is involved. [The proposed one-batch plan](NEXT_TRIAL.md) specifies
`deepseek-flash`, 80 dispatches and USD 0.70 local reservation cap, explicitly
distinguishes the unknown supplier hard cap, and requires a new approval. It has
**not** been executed.

**NOT_RUN:** real post-fix efficacy/quality/cost change, independent human
agreement, SQL holdout, expansion 60/300 and learning effects.
