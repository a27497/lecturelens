# Fresh development batch: frozen data and no-cost preflight

**Ready for a separately authorized, bounded real trial; real quality is NOT_RUN.**
The new set is **2 development courses / 4 complete sessions / 16 scheduled turns**,
8 per course. Candidate behavior was not changed. No SQL holdout question/material,
real model, external embedding/reviewer, account/billing API or new course download
was used. Previous paid authorization was not reused.

This is Codex-authored and Codex source-reviewed data, not independent human expert
annotation or an unseen-course holdout. The current candidate's earlier eight-turn
results remain historical context, not this batch's selection/optimization signal.
No new question, reference or threshold was changed after candidate Mock execution.

## Frozen identity and reproducible scope

- Started clean at `b96157fbd0107efd793a9fb03b17f1776a3ce8ea`, branch
  `codex/tutor-scale-preparation`, in the requested worktree.
- Pre-authoring identity/sources commit: **`d1971c3`**. Candidate remains
  `p8-tutor-grounded-v11-development`, `GroundedTutorRuntime`, adjacent-source
  passages v1; chained manifest
  `b7fe50df1854703cc05d4ad039dad3245cc62adc5d68c3af7b394f2407f0ec58`.
  Source v11 is identical to task-start code. Product default, prompts, historical
  identities, datasets, scores, original outputs and CI were not changed.
- Data, source review, gate and adapter were committed **before** candidate Mock:
  **`f318b3f56cd954464eef7afb789893d6c2c92e38`**. This is the actual full/fault Mock
  execution version. Final delivery adds only this report and non-sensitive
  verification metadata; executable code and frozen inputs remain identical.
- Dataset `tutor-fresh-dev-v1`, dataset-lock SHA-256
  `0531ce203d858c71d91fb3f61b1651e5e4af8cc1a781b3f3de4a4939456626a3`.
- [Batch plan](batch-plan.json) SHA-256
  **`4efdabb65a323155366184523757779a04b7ddfc7baf6717638590bdb91100ad`**.
  [Freeze lock](freeze-lock.json) SHA-256
  `54eb80db64b3c54b246b38dd26ddd6ab07d6cb5a8fa4304597c0d19a699c59d8`.
  `execution_authorized` stays false: data integrity is not spending authority.

| Execution part | Development course | Complete session | Turns | Focus and source lines |
| --- | --- | --- | ---: | --- |
| A | Programming with Python | `fresh-python-tail` | 5 | Negative string endpoints/interior slice, short suffix, unsupported Unicode extension, documentation discovery; 486–493, 512–563, 359–374 |
| A | Spreadsheets for Ecologists | `fresh-sheets-text` | 3 | Pasted text export failures, safe handoff and missing importer evidence; 288–299, 201–209, 305–320 |
| B | Programming with Python | `fresh-python-functions` | 3 | No-explicit-input calls, historical example time, whole-array multiple assignment and unavailable local-file diagnosis; 298–356, 379–403 |
| B | Spreadsheets for Ecologists | `fresh-sheets-markers` | 5 | Null-marker table, observed NA clarification, documentation, unsupported loader guarantee, compatibility vs recommendation; 99–112, 139–161, 305–320 |

A course is one published unit identity; a session is one complete conversation;
a turn is one planned learner message and its result, even if failed/missing.
Requests, repairs and ledger events are separate counts. Fixed order is A then B;
there is no budget-derived truncation of scope or fallback to old/full/SQL data.

The [source manifest](sources.json) preserves original/pinned URLs, revision,
acquisition time, source/license hashes and attribution. Python's pinned revision
is `eb18f246aee338b2a6169ba18d8c5ced7cf89f53`; each spreadsheet value is recorded
independently in the manifest. Existing unmodified Markdown and per-course LICENSE
files remain under `eval/tutor-public-v1/materials/`. Instructional text is CC BY 4.0;
code examples MIT. Carpentries/contributor credit and MANTRA/Edinburgh metadata
attribution remain. No linked media, data file or destination article was copied.
New questions and evidence adaptations are attributed CC BY 4.0 contributions.

## Content review, novelty and scoring gate

[CONTENT_REVIEW.json](CONTENT_REVIEW.json) records all 16 source checks and
per-turn substantive novelty/overlap. All references resolve to exact original
Markdown lines and pinned URLs. Negative tasks have positive scope anchors **and**
specific whole-unit/context reasons the requested fact is unavailable. Text-only
evidence never receives invented media timestamps.

There are **12 answerable / 4 insufficient** turns and **10 context-dependent**
turns. Nine turns carry the ordinary-task tag; categories overlap with multi-part,
clarification and boundary requirements rather than forming a repeated five-step
template. Three index/slice tasks exercise negative-string endpoint/short-input
semantics, not the old patient-ordinal question with changed numbers. Ordinary
documentation, function-call, multiple-assignment, export-risk and marker-table
tasks prevent the batch being solely old-defect stress cases.

Previously unasked details include negative suffixes for short input, function
discovery/no-input calls, pasted-character export risks, several null-marker table
rows and compatibility versus recommendation. Generic indexing, missingness,
metadata and refusal principles overlap old development tasks. Metadata location
itself is not claimed novel. All source units were available to earlier retrieval;
the review's line-overlap counts indicate prior reference coverage only, not prior
model exposure. Base-model training exposure is unknown. This set cannot establish
fresh-course generalization or be treated as an independent holdout after tuning.

Specific ambiguity checks: the plain-interpreter help workflow is reported as the
course's example, not guaranteed installed behavior; the historical time output
does not determine today's clock; the marker table is guidance about spreadsheet
encodings, not universal Python/SQL runtime semantics. The clarified real NA region
must not be erased as missing. No recipe, local CSV error or importer setting is
invented when source/context lacks it. Complete correctness includes all requested
parts and material added assertions; uncertain additions do not become passes.

[grading-rules.json](grading-rules.json) was frozen before any candidate execution:

- All 16 complete and source-reviewed, failed/missing 0; complete correct ≥14/16
  and ≥7/8 for each course.
- Index/slice critical cases 3/3; expected clean refusals 4/4; explicit clarification
  1/1; semantic cross-turn consistency ≥9/10.
- Supported explicit claim–citation pairs / **all** annotated pairs ≥0.95;
  supported required assertions / all citation-requiring assertions ≥0.90;
  expected-answer turns with full supported coverage ≥10/12. Report presence
  coverage too. Wrong refusals, uncited answers, failed and missing turns cannot
  improve expected-answer coverage.
- Every material optional assertion enters review. Uncertain pairs remain in the
  pair denominator; absent labels/inventories block a decision. Zero pairs/labels
  produce null/NOT_RUN, never PASS. Reviewer remains off; no artificial agreement.

These are predeclared engineering risk tolerances (at most one task error per
eight course turns, zero tolerated critical-index/refusal errors), not fitted
thresholds, statistical significance or a learning-effect claim. This report does
not evaluate that gate: it contains no semantic quality labels from Mock output.

## Actual no-cost verification

Raw evidence root:
`/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens/.data/tutor-fresh-dev-v1-20261107/`.

| Check | Actual result | Evidence under raw root |
| --- | --- | --- |
| Frozen v11 and historical tooling pins; two-course projection/reference validation | PASS; exact candidate and source/license hashes, no mixed authoring/holdout import | `verification.json`; `CONTENT_REVIEW.json` in repository |
| Targeted tests | **20 passed**, no skips; frozen unit selection | `frozen-unit.log`, `frozen-unit.xml` |
| Ruff check/format for new eval adapters | PASS; product files untouched | `verification.json` |
| Full frozen Mock batch | **16 expected/executed/completed; 0 failed/missing; 32 Mock requests; 64 ledger events; 0 reviewer calls** | `fresh-mock16/`, `checks/fresh-mock16/` |
| First-request synthetic timeout | Expected stop: **0 complete, 1 failed, 15 missing**, B not started | `timeout-check/`, `negative-checks.json` |
| Total cap 2, allocated 1 per part | Expected stop: one reserved/successful Mock search; next attempt denied before send; **1 failed, 15 missing**, B not started | `call-cap-check/` |
| Tiny explicit Mock money envelope | Expected stop before send: **0 reservations, 1 failed, 15 missing**, B not started | `money-cap-check/` |
| Independent PG/JSONL and turn reconciliation | PASS; **68 complete ledger event contents**, not just counts; **19 executed turn records** compared on input, answer/evaluation, outcome/status, citations, usage, execution counters and error | `independent-reconciliation.json`, `postgres-new-records.json`, `reconcile.py` |
| Isolation and cleanup | PASS; dedicated PG restored to exited 0, volume retained, 25841 closed; 23 preexisting running containers still running | `db-preflight.json`, `cleanup.json`, socket-fence records |

Full Mock expected-answer/refusal outcomes are 12/4 **oracle fixture behavior**,
not model task correctness. It uses the existing deterministic Mock transport,
including expected-negative membership. Fake 120/80 usage and local fixture
accounting are not real tokens or costs. All empty-label task/citation scores and
agreement/kappa stay null/NOT_RUN. Positive semantic judgments were not fabricated.

Failure cases are separate mechanism fixtures, not three extra quality attempts or
an expansion of the 16-turn dataset. Their whole-batch expected queue and diagnostic
census retain all 16 turns; failure does not silently drop B. Calls denied before
send are separate from reserved/sent requests. Every actual reserved/failed request
and bounded repair remains in accounting. No quality-driven rerun occurred.

The new wrapper reuses the original eight-turn execution function in two fixed
parts, with half of explicit total caps preallocated to each ledger. Core
request/provider/runtime/prompt/context/repair/store/metadata/scoring behavior is
unchanged. The small compatibility bridge extracts only five pinned pure public
utilities because the old module eagerly imports mixed-split questions. Old
selection and mixed/SQL file reads fail closed. References, rubric, answerability
and expected labels are absent from candidate request payloads; published worked
solutions remain legitimate course text. New snapshots contain only the two
permitted courses. No embeddings or Java/browser stack were needed.

The dedicated database's compose path, pinned image, loopback port, sole volume
consumer, no dependencies, 0.5 CPU/384 MiB limits and resources were checked before
start. All persisted records use new synthetic namespaces. No existing scope/run
was reused. PG exports contain only this task's new records, not SQL holdout text.
Python socket fence/environment stripping were used; libpq bypasses Python socket
counters, so actual PG row/ledger checks supply database evidence. No host-wide
packet attribution is claimed.

One initial **read-only audit helper** failed before connection because it referred
to a non-exported `legacy.psycopg`; its local import was corrected. The failed
helper record remains `audit-initial-failure.txt`; original full/fault results and
frozen candidate/data/adapters were not changed or rerun. Authoring lint cleanup
preceded final freeze; both unit runs passed. No unresolved data-quality or Mock
mechanics blocker remains. Broader UI/product suites were not repeated because
product code/behavior is unchanged.

## Next execution boundary

The [execution sheet](EXECUTION_SHEET.md) proposes the same requested
`deepseek-flash` route/settings as the old v11 trial, reviewer off, concurrency 1,
transport/application retries 0, no SDK, unchanged bounded repairs. Normal requests
**32**, second-search path **48**, theoretical maximum **80**. The two complete
parts are selected in advance, never by running out of budget. Moving-alias drift
and generation randomness limit old/new comparisons; tasks and
claim inventories also differ, so scores are not a paired improvement estimate.

Before real execution the user must separately confirm the exact API/model alias
and version limitation, numeric total request cap (proposed 80, not approved),
new total USD amount and supplier-billing limitation. Tool ceiling ≤USD 0.70 is
**not** authorized money or expected spend. Current prices, balance, actual access
and supplier-side bill protection are **UNKNOWN**; no checks were made. Fresh
pricing incompatible with frozen local accounting blocks the live entry rather
than changing old rates. Local pre-reservation cannot guarantee the supplier bill
hard cap. There is no runnable unbudgeted real command or automatic continuation.

**NOT_RUN:** real requests/quality, real token use/cost or cost change, real reviewer,
independent human agreement/kappa, SQL candidate evaluation, new courses, 60/300/320
turn expansion and learning outcomes. The task ends at local commit, with no
push/PR/merge/deployment/CI or candidate change and no scheduled next batch.
