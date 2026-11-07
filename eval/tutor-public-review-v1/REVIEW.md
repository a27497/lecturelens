# Public-course dataset source audit v1

**Decision: OTHER BLOCKER — resolve the Tutor instruction/reference notation conflict before freezing a trial.**
No paid-trial scope manifest is created. No frozen data, runtime, prompt, old record or scoring implementation
was changed. This is a second source-based **Codex** review, in the same conversation as prior authoring;
it is not author-blind, independent human subject-expert review or human gold annotation.

Checked clean HEAD `64c0f48f832073480a9d40ccd67178d7bdc58579` on `codex/tutor-scale-preparation`, in
`/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens`. Read AGENTS.md, public dataset README/REPORT,
the relevant v2 contracts and original source materials. No other checkout or account was inspected.

## Source and license checks

Each course was checked against **its own** published license page and its own same-revision LICENSE.md,
not inferred from a single sibling course. Unauthenticated re-fetches of all three pinned Markdown files
and all three pinned LICENSE.md files matched both the manifest and saved bytes. See
[SOURCE_VERIFICATION.json](SOURCE_VERIFICATION.json) for URLs, HTTP destinations, dates and exact hashes.

| Course / split | Fixed source revision | Course-specific license evidence |
| --- | --- | --- |
| Programming with Python / development | `eb18f246aee338b2a6169ba18d8c5ced7cf89f53` | [Lesson license](https://swcarpentry.github.io/python-novice-inflammation/LICENSE.html), [pinned license](https://raw.githubusercontent.com/swcarpentry/python-novice-inflammation/eb18f246aee338b2a6169ba18d8c5ced7cf89f53/LICENSE.md) |
| Spreadsheets for Ecologists / development | `78a54d7a7adcc961e83f463ba5392232e035cc6c` | [Lesson license](https://datacarpentry.github.io/spreadsheet-ecology-lesson/LICENSE.html), [pinned license](https://raw.githubusercontent.com/datacarpentry/spreadsheet-ecology-lesson/78a54d7a7adcc961e83f463ba5392232e035cc6c/LICENSE.md) |
| Databases and SQL / holdout | `0d101a4cc2ce7638dfa18289b55f7ab47f44a3ee` | [Lesson license](https://swcarpentry.github.io/sql-novice-survey/LICENSE.html), [pinned license](https://raw.githubusercontent.com/swcarpentry/sql-novice-survey/0d101a4cc2ce7638dfa18289b55f7ab47f44a3ee/LICENSE.md) |

The retained instructional prose is covered by CC BY 4.0; example software is MIT. Copyright attribution,
license links, changes and MIT permission notices are retained. The spreadsheet metadata section explicitly
attributes Research Data MANTRA; [MANTRA's own licence page](https://mantra.ed.ac.uk/acknowledgements.html)
independently confirms compatible CC BY 4.0 and its author/URL requirements. The retained text preserves that
credit. Other destination articles, images and media were not copied; links in Markdown do not constitute
those files being present. No conflicting restriction was found in the retained text/license notices.

## Development content review

Completed source-based review of **all 8 development sessions / 40 turns**, not just the prospective smallest
sessions. [DEVELOPMENT_REVIEW.json](DEVELOPMENT_REVIEW.json) records each turn's source ranges, answerability,
context dependencies, disposition and substantive review note. All reference points and permitted alternatives
were checked against the original units. Structural checks independently resolved **274 development quote
locations** back to original line bytes and their own course evidence. IDs and earlier-turn dependencies are valid.

No independently incorrect reference fact or unsupported mandatory answer point was found. The 30 answerable
turns, 6 insufficient-evidence turns and 4 outside-unit turns are distinguishable. Nine development false-premise
turns request corrections rather than rewarding agreement. Negative cases identify absent environment,
benchmark, specimen, team-specific formula or method evidence; nearby quotes are scope anchors, not proof of
universal absence. Clean course-bound refusal is acceptable, so explanatory text is not mandatory when the
runtime uses its canonical abstention.

Questions state the relevant learner scenario. Follow-ups change assumptions, reduced axes, representations
or requested scope; no repeated fixed five-category conversation sequence was found. Some quoted code/false
claims intentionally appear in learner inputs for diagnosis; this is not hidden-reference leakage. The request
builder excludes authored references/rubrics/expected labels. Published worked course solutions remain normal
instructional evidence. These observations do not establish that all questions are equally difficult or natural.

Existing source defects are adequately limited by the frozen answer boundaries:

- Python source line 438 loosely calls shape `(60,)` an N-by-1 vector and mixes daily/patient wording.
  `python-03:3` requires the printed 1D shape and correct reduced-versus-retained axes.
- Spreadsheet lines 88–91 overgeneralize null propagation in a mean; lines 99–105 qualify software behaviour.
  `sheets-02:4` explicitly tests the qualification, rather than scoring the universal claim as true.
- Spreadsheet line 221 broadly warns against numbers in field names, while line 267 supplies `Observation_01`.
  `sheets-04:1` permits sensible digits and keeps the parser/leading-digit concern distinct.

Minor narrative caveat: `sheets-03:6` introduces “two suspect identifications” without an earlier exact count.
That is an unverified learner assertion, not source evidence; the correct refusal does not require deciding
which record is wrong. No mandatory scoring change is indicated by that wording alone.

## Issue list

**R1 — Blocking instruction/reference conflict for valid Python indexing.**

The actual Tutor system text, [runtime.py](../../agent-service/src/lecturelens_real_eval/tutor/runtime.py),
lines 27–40, tells the Tutor to reserve square brackets for citations and use parentheses for indexing. The
new tasks correctly ask for Python subscripts/slices, for which replacing brackets by parentheses changes
the meaning or yields invalid syntax. This is not an error in NumPy reference facts; it is an inconsistent
response-format contract that can contaminate scoring and instruction-following assessment.

| Turn | Required/reference form | Development JSON evidence | Original material |
| --- | --- | --- | --- |
| `python-01:3` | `data[29, 19]`; boundary explicitly requires an element expression | lines 357–360 | Python lines 181–219 |
| `python-02:1` | `data[0:4, 0:10]` or equivalent omitted lower bounds | lines 506–509 | Python lines 240–260 |
| `python-02:3` | `data[:3, 36:]`, with `data[:3, -4:]` also accepted | lines 674–677 | Python lines 276–294 |
| `python-04:4` | dimension-preserving slices in `hstack((A[:, :1], A[:, -1:]))` | lines 2070–2073 | Python lines 634–659 |

An offline check confirmed that `FinishInput` and `inline_citation_ids` accept the valid square-index form
and identify only the real evidence ID. Thus this is **not a hard parser/schema rejection**, and these four
turns are not claimed to inevitably fail. A model could ignore the instruction or offer an equivalent
description. However, `python-01:3` explicitly requires an expression, and there is no documented exception
for code in the system instruction. The trial would confound task ability with resolving an avoidable
instruction/rubric contradiction. A new scope is not frozen by silently excluding inconvenient tasks.

Recommendation only: in a separately authorized, newly versioned candidate, reconcile the instruction with
valid code notation, for example by allowing language syntax in code while retaining the citation-ID grammar.
Alternatively, a new task version could explicitly accept accurate language-only indexing descriptions when
code is not the skill being tested. Do not accept invalid `data(...)` as valid NumPy, mutate this frozen set,
or overwrite the old candidate/results. Add a targeted offline valid-code/citation coexistence check before
real execution. This audit implements none of these repairs.

**Execution prerequisite, already documented:** the public driver has no live switch, and public review loading
accepts Mock records only. There is no executable public-data real-trial adapter to which a scope-only JSON
would automatically apply. Enabling real execution or disabling the reviewer would need a separately reviewed
minimal adapter, exact scope/hash checks and explicit authorization; the synthetic live entry point cannot
be used as a shortcut. This is not evidence that data references are wrong.

## Holdout boundary and capability coverage

SQL was checked only for its own license, pinned source/license hashes, structure, unique IDs, source-locator
membership, frozen manifest and course isolation. Mechanical validation resolved **100 holdout quote locations**;
that is not review of their semantic correctness. No SQL question/reference content was semantically reviewed,
no SQL output quality was scored, and no SQL candidate answer generation, model/tool loop or provider request
was executed. Regression fixtures exercise empty/missing packets and request serialization only. No policy/prompt
was tuned from holdout results.

Independently recounted total **3 courses / 12 sessions / 60 turns**, development 2/8/40 and holdout 1/4/20;
course identities are disjoint. The split first appears in `31acd91` with only two split files, before authored
questions. Public base-model exposure is unknown; this is not a never-seen-by-the-base-model claim.

This set can probe short English source-grounded explanations, code/array reasoning, spreadsheet data design,
false-premise correction, conversational referents/conditions, source citation support and refusal under a closed
unit boundary. These are prospective probes, not measured abilities. All tasks have Socratic mode disabled.
The bounded, closed-source search path does not establish general Agent planning or autonomous tool orchestration.
There is no real learner feedback cycle, adaptive teaching, mastery or learning-effect evidence. Text-only units
cannot establish video time localisation, ASR/transcript quality, Chinese-course effectiveness, long-course
retrieval, multimodal ingestion or broad disciplinary generalisation. All courses share one publisher and an
introductory research-computing orientation; source exercises include fictional teaching scenarios.

## Version delta and checks actually run

Full diff `035aa9c..64c0f48` contains exactly five paths: README.md, REPORT.md, verification.json,
public_review.py and test_public.py. Only the last two are executable/test changes. They retain the assigned
overlap denominator when annotations are absent and add NOT_RUN status. Runtime, driver, sources, dataset,
frozen split and old blind samples are unchanged. No full Mock rerun or database startup was necessary.

- Re-fetched six pinned public files and matched each against its own recorded/local SHA-256.
- Independently checked data locks, counts, disjoint courses, IDs, earlier-turn dependencies and source-line
  membership. Structure checks do not validate semantics; the 40 development semantic notes are separate.
- Ran two existing targeted tests under the socket-fenced launcher: census/overlap/empty-label regression and
  Tutor request-reference exclusion. **2 passed in 0.63 s**. Fixtures create no Tutor/provider responses.
- Recomputed empty-label task/citation denominators from **only the 40 development rows** of saved Mock records:
  expected answers 30, expected abstentions 10, contextual turns 27; assessed 0, valid model–human pairs 0,
  null ratios/kappa and NOT_RUN. No fabricated annotations or answer-quality judgments were introduced.
- Checked actual system instruction, response schema and citation parser on a constructed Python expression;
  independently checked small string/slice/difference arithmetic. No model or student data used.
- Rechecked hashes of 42 existing dataset/driver/doc/raw-run files; all unchanged. No DB/PG comparison was
  repeated this round; prior PG claims are not re-certified by this read-only audit.

Inspectable local audit logic/results: `.data/tutor-public-review-v1-20261107/`. Checked code version is
`64c0f48`; this review's commit adds reports/hash evidence only. [VERIFICATION.json](VERIFICATION.json)
records checks, provenance and artifact hashes. From repository root, reproduce input integrity with
`sha256sum -c eval/tutor-public-review-v1/INPUTS.sha256`; inspect DEVELOPMENT_REVIEW.json for all 40 dispositions.
This checksum verification does not run a candidate, start a database or constitute semantic expert approval.

## Future trial confirmations — not authorization

R1 must first be resolved and re-reviewed; **no session/turn execution manifest is frozen this round**. When
freezing one later, select exactly one whole session from each development course, record version/session/turn
IDs and source/data/task hashes, exclude SQL, and retain all planned turns after failure/budget stop.

The user must separately confirm:

1. Provider/endpoint and exact Tutor model ID/revision, plus returned-version handling. Static code currently
   pins the aliases `deepseek-flash` and `deepseek-v4-pro`; neither is a newly selected immutable model revision.
2. Reviewer enabled or disabled, and its exact ID if enabled. Current public Mock always runs a fake reviewer;
   a disabled reviewer is not an existing switch. Its support/context/clean-abstention labels do not replace
   independent task-correctness, refusal-correctness and context annotations.
3. Retry/repair policy and one total request hard ceiling across **both roles and all courses**, with no hidden
   HTTP retries or replay of unknown outcomes. Existing Tutor transport has no automatic network retry; normal
   one-search plus finish uses 2 calls, a second search uses 3, and bounded protocol repairs permit at most
   5 Tutor calls per turn. Reviewer normally uses 1 and allows at most 3 total attempts while the ledger remains
   unblocked. Therefore for N turns: simple normal 2N without reviewer / 3N with reviewer; two-search normal
   ceiling 3N / 4N; repair/retry planning ceiling 5N / 8N. These are static code bounds, not measured real calls.
   For **8 hypothetical turns only**, the latter are 40 / 64 calls, versus simple normal 16 / 24. Eight turns is
   an arithmetic example, not a selected manifest or approved spending limit. The actual total cap is UNCONFIRMED.
4. Currency and total money hard ceiling, current verified input/output/other billing rates with dated sources,
   reservation/token assumptions, partitioned ledger ceilings whose sum is within the authorized total, and stop
   behaviour for missing usage/prices/version or failed/unknown calls. Current prices and account balance are
   **UNKNOWN**; no account, credential or historical balance was inspected or reused.

Existing ledgers reserve before send, persist call/amount bounds, compare PG/JSONL and retain unknown reservations.
But their prices are hardcoded historical constants; the pricing-file check checks matching constants plus a
nonempty date/HTTPS URL, not current-price freshness or vendor authority. Reservation uses raw request bytes as
an input-token proxy plus bounded output tokens; settlement can discover excess reported usage **after** the
request and then block. A provider invoice hard ceiling is not proven without validated rates/token/billing
coverage and appropriate provider-side limits. The internal 0.70-per-ledger maximum is not an approved budget
or a current-price quote; the public Mock driver has no operator-supplied real money cap. A call count alone is
not a money limit. No present adapter/pricing/account state is certified for a paid run by this report.

**NOT_RUN:** real Tutor quality/citation accuracy/coverage, real reviewer, independent human/expert annotation,
human agreement/kappa, real tokens/cost, learning effects and any real trial. Await the user's separate model,
total-call and amount-budget confirmation after the blocking contract issue is resolved.
