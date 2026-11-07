# Fresh development v1: one real batch, 2026-11-07

**FAIL; do not expand evaluation yet.** The one authorized trial stopped in part A:
16 scheduled, 7 attempted, 6 completed, 1 failed and 9 missing. Part B was never
started. All 16 scheduled outcomes were reviewed against the original source and
frozen requirements; only six completed answers are semantically scorable. Codex
confirmed **3/16 complete correct**, with two incorrect completed answers and one
uncertain completed answer. There was no rerun, candidate fix, model substitution,
budget increase, SQL evaluation or subsequent batch.

This is **Codex nonblind source review**, not independent human blind assessment.
The data are fresh development tasks on two previously available public units,
not unseen-course or held-out generalization evidence. The old eight-turn trial
uses different questions, context and claim inventories; score differences are
not a controlled before/after improvement estimate.

## Frozen identity and authorization

- Worktree: `/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens`; branch
  `codex/tutor-scale-preparation`. Clean at the requested execution HEAD
  **`06b5858024b5b22cded0573dca7963c5a73b3d19`**.
- Actual execution identity: **`p8-tutor-grounded-v11-development`**,
  `lecturelens_real_eval.tutor.grounded_runtime:GroundedTutorRuntime`,
  `adjacent-source-passages-v1`. Candidate base source is `b96157f`; neither this
  task nor its observer changed the candidate, prompts or product defaults.
- Candidate manifest SHA-256:
  `b7fe50df1854703cc05d4ad039dad3245cc62adc5d68c3af7b394f2407f0ec58`.
- Batch-plan SHA-256:
  `4efdabb65a323155366184523757779a04b7ddfc7baf6717638590bdb91100ad`.
- Dataset-lock SHA-256:
  `0531ce203d858c71d91fb3f61b1651e5e4af8cc1a781b3f3de4a4939456626a3`.
- Freeze-lock SHA-256:
  `54eb80db64b3c54b246b38dd26ddd6ab07d6cb5a8fa4304597c0d19a699c59d8`.
- Scoring rules SHA-256:
  `0eb59ce214d5607205d1b3cb9b12090ea0ba00ef83455a01e4ff42e317e628ca`.
  Candidate/source/adapter pins and original reference quotations were reverified.
  No frozen file, question, reference, threshold or prior result was edited.
- The user authorized this exact 16-turn batch with **USD 10 maximum / 80 total
  model requests**, including failures and repairs. The unchanged entry accepts
  at most USD 0.70, so execution retained **USD 0.70 local ledger cap**, split into
  two fixed USD 0.35 / 40-request allocations. No unused allocation transfers.
  Authorization ends with this batch; unused money/calls authorize no continuation.
  Frozen proposal files keep their historical `execution_authorized: false`;
  this task's separate authorization record supplies the new conversational grant.

Requested API ID was **`deepseek-flash`**, only through
`https://api.deepseek.com/chat/completions`. Temperature 0, thinking disabled,
maximum output 1,200 tokens/request, reviewer off, concurrency 1,
SDK/application/transport retries 0. Existing bounded format/mode repairs and all
persistent runtime/session/ledger guards remained active.

All 17 responses returned model **`deepseek-flash`**, with one common reported
fingerprint, 17 unique response IDs and no request-ID header. The official page
currently describes `DeepSeek-V4.1-Flash-1017`; that documentation and the returned
alias/fingerprint do **not** verify an immutable API model version. Alias drift
and generation randomness remain limitations. Missing identifiers are explicitly
UNKNOWN, not invented.

## Actual execution and stop

One supervised run occurred **20:35:30–20:36:02 Asia/Shanghai**
(12:35:30–12:36:02 UTC); supervisor duration 32.594 seconds, exit 1 for incomplete
execution, with a terminal record and no timeout. A private observer recorded exact
request bodies after normal reservation and before forwarding unchanged bytes.
Only transport observation was injected; candidate/runtime and frozen adapters on
disk were unchanged. A synthetic observer check verified byte preservation and
its send cap without a model request. The dedicated sender consumed the already
provisioned evaluation secret; no credential value entered chat, argv, evidence,
logs or Git. No connectivity probe, account query or embedding/reviewer call ran.

The final attempted turn, **`fresh-sheets-text:2`**, proposed an answer of **1,601
characters / five distinct cited IDs**, exceeding the frozen 1,600-character /
four-ID bounds. All proposed IDs were observed and authorized. Its existing
format-repair preparation required another **23,897 runtime byte-proxy units**;
45,053 were already reserved for that turn. The sum **68,950 > 64,000** failed
`TUTOR_REPAIR_BUDGET_UNAVAILABLE` before a repair observation or fourth request
could commit. Session call/token-proxy limits were not exhausted. These units are
serialized-context reservation proxies, **not provider tokens**. An offline
source reconstruction records the individual conditions; it sent no request and
did not resume or replay the failed turn.

The USD/request ceilings did not cause this stop. The batch correctly stopped on
the first failed turn, leaving the remaining part-A turn and all eight part-B
turns missing. The unpublished draft is retained and separately source-reviewed;
it is not a successful answer. No repair request was sent anywhere in the batch.

| Execution unit | Result |
| --- | ---: |
| Scheduled courses / sessions / turns | 2 / 4 / 16 |
| Attempted courses / sessions; complete sessions | 2 / 2; 1 |
| Expected / attempted / completed / failed / missing turns | 16 / 7 / 6 / 1 / 9 |
| Scorable / semantically scored completed answers | 6 / 6 |
| All scheduled outcomes reviewed; failed draft reviewed separately | 16; 1 |
| Real HTTP requests / HTTP 200 / failed HTTP requests | 17 / 17 / 0 |
| Executed local searches / model finish decisions | 10 / 7 |
| Ignored extra tool proposal / extra paid request caused by it | 1 / 0 |
| Repair requests / reviewer requests / transport retries | 0 / 0 / 0 |
| Reserved-and-settled calls / ledger events / pending calls | 17 / 34 / 0 |

## Full source review and frozen gate

The claim inventory contains **29 distinct assertions**, of which **25 require
citations**, and **21 explicit substantive claim–citation pairs**. Repeated
code/results and repeated claims with the same source are deduplicated. Citations
attach locally; an explicit closing worked-example/list citation may cover that
example/list, but unrelated neighboring citations are not inherited. Scope
caveats, conversation references and clean refusals are checked for truth without
inventing positive-citation requirements for absence statements. Material optional
assertions remain in the applicable claim/task denominators.

All 16 frozen reference inventories were checked against original Markdown lines.
Missing outputs receive no semantic answer labels; failure/missing cannot improve
task or turn-coverage scores. The failed draft's claims are a separate diagnostic
inventory, excluded from published-answer citation ratios and every success count.
Its separate-note-field and associated same-directory metadata guidance is mostly
grounded, but it has no published answer and omits an explicit simple-cell
restatement. It cannot be promoted to a completed correct turn.

| Frozen condition | Observed | Result |
| --- | --- | --- |
| Complete/review 16; failed/missing 0 | 6 completed; all 16 outcome reviews; 1 failed, 9 missing | FAIL |
| Complete correct at least 14/16 | **3/16**; completed judgments 3 correct / 2 incorrect / 1 uncertain | FAIL |
| Each course at least 7/8 complete correct | Python **2/8**; spreadsheets **1/8** | FAIL |
| Critical index/slice complete correct 3/3 | **0/3 confirmed**; required core outputs 3/3, optional-claim defects remain | FAIL |
| Expected clean refusals 4/4 | **1/4**; 1 observed correct, 3 missing | FAIL |
| Explicit clarification 1/1 | **0/1**, turn missing | FAIL |
| Semantic context consistency at least 9/10 | **3/10 verified**; 3/3 observed completed follow-ups consistent, 7 unverified | FAIL |
| Supported claim–citation pairs at least 0.95 | **18/21 = 85.71%**; 3 unsupported, 0 uncertain pairs | FAIL |
| Citation presence, reported separately | **21/25 = 84.00%** | Descriptive |
| Supported claim coverage at least 0.90 | **18/25 = 72.00%** | FAIL |
| Fully supported expected-answer turns at least 10/12 | **1/12**; only Python tail 5 covers every citation-requiring assertion | FAIL |

Five answerable turns and one expected-refusal turn completed. All five answerable
cores include their frozen requested points; this does not erase added false or
uncertain assertions. Two of the five are verified complete correct answers and
one clean refusal is correct. No wrong refusal was observed among the completed
answerable turns. Failed/missing answerable turns remain in the 12-turn coverage
denominator. Claim ratios describe available published content, not the absent
answers or full-batch reliability.

| Scheduled turn | Source review / disposition |
| --- | --- |
| `fresh-python-tail:1` | **Incorrect full answer; core complete.** Correct `n`, `e`, `xyge` and excluded endpoint. Added assertion that the unit does not explicitly define `element[-1]`/`[-2]` contradicts original lines 512–522, which print `n` and `e`. Two separate output bullets lack local citations. Retrieved excerpts omitted that block; missing retrieval is not whole-unit absence. |
| `fresh-python-tail:2` | **Incorrect full answer; core complete.** Correct `[-3:]`, `try`, `hi`, with no padding. Added claim that `[3:6]` “only works” for oxygen is false for other six-character strings. The final negative-start/open-stop explanation cites the question/interior-slice passage, not the suffix solution. Actual prior context is retained. |
| `fresh-python-tail:3` | **Uncertain full answer; core complete.** Correct no-padding correction and consistent prior `hi` result. The phrase attributed to the course as its own framing, “when available,” is not in that cited passage; it came from the learner question. Behavior is right, literal course attribution is unverified. No full-pass credit; the source-fidelity defect is retained rather than relabelled as a wrong short-string output. |
| `fresh-python-tail:4` | **Correct clean refusal.** No Unicode grapheme-reversal algorithm or unsupported recipe supplied. Context retained. |
| `fresh-python-tail:5` | **Correct.** Covers NumPy-dot/Tab, trailing `?`, equivalent `help`, and plain-interpreter double Tab/help as the lesson's procedure. Topic transition handled; no claim to inspect local completion configuration. |
| `fresh-sheets-text:1` | **Correct with coverage gap.** Names both split-line and encoding errors plus newline/tab/vertical-tab/plain-cell restrictions. Final uncited strip/replace advice is a bounded application, not a promised lossless repair; it remains in the coverage denominator. |
| `fresh-sheets-text:2` | **Failed; no final answer.** Draft source review preserved separately. Format limits trigger a repair whose persistent turn reservation cannot fit. Cannot credit draft as correct, consistent or covered final output. |
| `fresh-sheets-text:3` | **Missing.** No lost-record/encoding/importer diagnosis or refusal observed. Frozen original/logs insufficiency rationale checked; no semantic score invented. |
| `fresh-python-functions:1` | **Missing.** Mean input, no-explicit-argument `ctime`, parentheses and historical timestamp requirements checked against 298–334; no output to score. |
| `fresh-python-functions:2` | **Missing.** Whole-array assignment and 20.0 / 0.0 / 4.61383319712 versus per-patient maxima requirements checked against 338–403; no output to score. |
| `fresh-python-functions:3` | **Missing.** No local CSV/cell diagnosis or refusal observed; missing-file insufficiency rationale retained. |
| `fresh-sheets-markers:1` | **Missing.** Original NA/na, N/A, NULL problems and recommendations at 139–155 checked; no marker comparison observed. |
| `fresh-sheets-markers:2` | **Missing.** Real NA/North America clarification checked against 103–108 and 139–143; no evidence of preserving that observation. |
| `fresh-sheets-markers:3` | **Missing.** Same-directory, clearly associated plain-text metadata and null-convention requirements at 103–108 and 305–320 checked; no answer observed. |
| `fresh-sheets-markers:4` | **Missing.** No loader flag or losslessness guarantee/refusal observed; loader/configuration insufficiency remains. |
| `fresh-sheets-markers:5` | **Missing.** None/Python compatibility versus Avoid/uncommon/type-problem distinction at 157–161 checked; no answer observed. |

The main remaining blockers are false source-scope/exclusivity additions,
misattached or uncited substantive explanations, and a legitimate multi-part
handoff answer that cannot fit the existing output/repair reservation envelope.
The stopped batch provides no evidence on function summaries, NA clarification
or compatibility interpretation. **Do not proceed directly to 300 turns or SQL**.
A separately scoped future engineering task could address these blockers, but
this task performs no fix, new data authoring, further trial or automatic expansion.

## Tokens, rates and local accounting

The [official DeepSeek pricing page](https://api-docs.deepseek.com/quick_start/pricing/)
was reopened on 2026-11-07 and its public HTML/hash retained. Peak input-miss and
output rates remain compatible with the frozen ledger. The same observation
records published cache/off-peak rates; no historical price file was changed.
Requests were on a UTC Saturday, for which the published weekend rule gives
off-peak rates. Pricing/access and discounts are not account-billing evidence.

| Provider-reported usage | Tokens |
| --- | ---: |
| Input | **61,668** |
| Output | **3,460** |
| Total | **65,128** |
| Input cache hit / miss | **16,896 / 44,772** |

Per million tokens, the retained observation uses off-peak cache hit USD 0.003,
cache miss USD 0.15 and output USD 0.60. Therefore:

`(16,896 × 0.003 + 44,772 × 0.15 + 3,460 × 0.60) / 1,000,000 = USD 0.008842488`.

This is **provider-reported usage multiplied by observed public rates**, not an
actual supplier invoice. Actual account debit, balance, credits and supplier bill
hard cap are **UNKNOWN / not queried**. Missing request-ID headers stay UNKNOWN;
all 17 response IDs, model aliases, numeric usage/cache fields and fingerprints
were captured without anomalies.

The local ledger deliberately ignores cache/discounts and uses peak input-miss
USD 0.30 / output USD 1.20 per million:

`(61,668 × 0.30 + 3,460 × 1.20) / 1,000,000 = USD 0.0226524`.

That equals **22,652,400 nano-USD** across 17 settled reservations. Maximum observed
reservation-prefix exposure was **USD 0.0278595**; pending 0, blocked null, mirrors
identical. All failures/unsuccessful finish decisions are included. This is below
the effective USD 0.70 local envelope and authorized USD 10 upper limit on the
known rate/usage basis; the ledger's UTF-8 byte proxy and local enforcement do
**not guarantee the supplier's actual invoice ceiling**. No remaining allowance
is available for a subsequent batch under this authorization.

## Evidence, validation and cleanup

Private raw root:
`/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens/.data/tutor-fresh-live-20261107/`.

- `fresh-real16/`: original global/part configs, all 16 expected/result rows,
  failed/missing census, partial turns, part-A calls and mirrored ledger; B absent.
- `wire/001-request.json` through `017-request.json`, `wire-events.jsonl`:
  exact prompts, actual conversation/context, observations and retrieved text.
- `turn-dossiers.json`: all 16 questions/statuses, request paths, parsed proposals,
  answers, errors, IDs, model/usage/cache metadata, repair explanation and reviews;
  unexecuted/missing fields explicitly UNKNOWN.
- `postgres-run-snapshot.json`, `reconciliation.json`: only this trial's two
  synthetic sessions/seven turns/one ledger run. All 34 PG ledger event contents
  match JSONL, seven stored turn contents match results, and 17 request hashes
  match wire/call/reservation records. Every retrieved passage matches its frozen
  original blocks; final cited IDs were observed this turn. Reference/rubric
  fields were absent from actual model contexts.
- `codex-source-review.json`, `failed-draft-source-review.json`, `review-audit.json`:
  final claim inventories, original quotations, pair labels, per-requirement
  assessments, all denominators and gate arithmetic. No model reviewer labels.
- `authorization.json`, `preflight.json`, `pricing-observation.json`,
  `official-pricing.html`, `execution-start.json`, `execution-end.json`,
  `stop-diagnosis.json`, `checks/`, `cleanup.json`: authority, identity, source,
  process, budget/stop and resource lifecycle evidence. `artifact-manifest.json`
  hashes private evidence; the public summary contains its digest.

Preparation helpers had two read-only failures around an overbroad hash scan/file
assumption; the existing SQL/mixed-scope fence prevented the forbidden file read.
A post-run diagnostic import and a provenance audit assuming wire-only metadata
also failed before their outputs were created; helpers were corrected locally.
No such failure sent a model request, changed frozen code or reran the trial.
An initial hand-enumerated full-coverage subtotal of 2 was replaced with automatic
arithmetic over the unchanged complete inventory, giving **1/12**; the initial
derivative is retained. No semantic labels, questions, thresholds or references
were changed to improve scores. Original runner summaries retain their unannotated
`NOT_RUN` quality placeholders; later reconciliation/review is recorded separately.

The dedicated database's compose path, pinned image, sole volume consumer, no
dependencies, free loopback port 25841, 0.5 CPU/384 MiB limits and resources were
verified before start. It is now **exited 0**, port closed, volume retained; all
23 preexisting containers remain running. Existing 2,011 allowed tracked files
were hash-checked unchanged; protected SQL/mixed-scope files were excluded from
content inspection. Only these new report/summary files are committed. No runtime
change required a new runtime regression suite; frozen preparation, observer
mechanics and the actual PG/JSONL/wire/quotation checks supply this task's relevant
verification. They do not replace model task-quality review or imply a full
Python/PostgreSQL suite was run.

**NOT_RUN:** independent human agreement/kappa, SQL holdout, 300-turn expansion,
new-course generalization, real model reviewer, learning effects, supplier
invoice/balance verification, broader service/browser regression suites. No
production/student data, default identity, CI, other workspace's changes, push,
PR, merge, deployment or rented server was touched.
