# Public-course dataset v1 preparation record

Prepared on 2026-11-07 in `/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens`, branch
`codex/tutor-scale-preparation`. Initial HEAD was the clean `2e862b82ae0c8592f301d62a0083ad24db512fff`.
All changes are confined to `eval/tutor-public-v1/`; no product/runtime/CI, old frozen asset, original result,
other checkout, deployment, provider account, push or PR was changed or used.

## Data and content review

Three real Carpentries courses, complete English textual units: Python/NumPy array analysis, spreadsheet
formatting for ecologists, and SQL filtering. Teaching prose CC BY 4.0, software examples MIT. Original Markdown
and same-revision license files are retained unchanged. [sources.json](sources.json) contains immutable download
URLs, source revisions, dates, SHA-256 and attribution; the compatible MANTRA secondary credit is retained.
No external images, data files or video were fetched. See [README.md](README.md) for source/license links.

The course/session split was frozen first in commit `31acd91`, before questions or adapter debugging. Python
and spreadsheets: **2 development courses / 8 sessions / 40 turns**. SQL: **1 evaluation-only course holdout /
4 sessions / 20 turns**. Total **3 / 12 / 60**, balanced 20 turns per course. Twelve distinct category sequences,
session lengths 4–6, 40 declared contextual turns; 45 answerable, 10 insufficient-evidence, 5 outside-unit;
12 false-premise turns are part of the answerable population. Requests/events are not dialogue turns.

Every reference has source-line quotes, expected points, allowed alternatives, insufficiency rationale where
needed, and task/citation/context criteria. [CONTENT_REVIEW.md](CONTENT_REVIEW.md) records the per-turn ledger
and source inaccuracies/ambiguities handled in grading boundaries. Whole-unit source and conversational review
was performed by **Codex**, the same author as the tasks. It is not independent human expert annotation. The
holdout was viewed for evaluation authoring/source audit and Mock compatibility, never Tutor prompt/product tuning.
Public source exposure of a base model remains unknown. The split is procedural, not a confidential access control.

## Reuse and compatibility changes

Preserved the original synthetic suite and v2 fixed queue/random sample. Reused their frozen runtime/store,
source authority/provider, recorded Mock channel, reserve-before-send ledger, annotation validator/importer,
claim/pair scoring and full scheduled task/refusal/context denominators. New adapters only supply the public
dataset, explicit complete-course/session selection and a 60/12 census review design; old entry points hardcode
synthetic counts/scope. No platform or product refactor. Public execution has no live switch, always constructs
MockTransport, uses live=false and requires the existing clean socket-fenced launcher.

The raw source's original trailing whitespace/blank lines are deliberately retained; Git whitespace warnings
inside `materials/` are expected. All generated/new executable files pass their checks. A pre-freeze formatter
attempt changed Python snippets inside Markdown; source hash validation caught it, the exact upstream bytes
were restored, and formatting was subsequently limited to `*.py`. References/hashes were not altered to accept
modified source bytes. No committed dataset/source changed after the dataset commit `af1632f`.

## Executed verification

- Offline data/projection validation and independent JSON recount: **3 courses, 12 sessions, 60 unique turns**,
  40/20 split, no shared course identity, exact source/license hashes, quote line-byte resolution and dependency
  validity. All twelve task-category sequences differ. Snapshot has no authored answer/rubric fields; a test
  exercises the actual Tutor request builder for all 60 learner inputs to check evaluator labels stay outside.
- **44 tests passed**, comprising 10 new public-set tests, 23 v2 tests and 11 v1 tool tests. Final supervised
  run: `.data/dev-checks/tutor-public-tests-r2-20261107/`, 4.27 seconds. Checks include deliberate source/split/
  version corruption rejection, course/session selection and holdout opt-in, exclusive deterministic projection,
  all-missing/failed result retention, census blinding/reproducibility, overlap and empty annotation denominators.
  Existing hand-constructed arithmetic/agreement tests passed; no actual semantic labels were inferred.
- Ruff check/format on **new Python files only** passed. Source Markdown is not a formatting target.
- Mock development smoke explicitly selected `carpentries-python` + complete `python-01`: **4 turns / 12
  simulated requests / 24 ledger events**, no holdout execution, no missing/failure/review error.
- Full bounded Mock: **60 completed / 0 failed / 0 missing**, **180 simulated requests / 360 events**
  (180 reserved, 180 settled), no pending/unknown accounting or review failures. Completion means protocol only.
  All three text courses load; raw per-course and aggregate turns/calls and config/data/code identity are saved.
- Independent read-only PG audit compared **all 360 ordered event JSON objects**, not just event counts, and
  all 60 turns' session, ordinal, learner text/mode, status/outcome, answer/evaluation, error, usage, model/tool
  counts, reservations and canonical citation fields against JSONL. Checkpoint content was not exported by the
  legacy GET interface and was **not** included in the per-turn equality assertion. Raw/aggregate/call mirrors
  also matched. Preexisting record hashes remained unchanged: 200 non-new-owner sessions, 954 turns, 57
  non-new-prefix runs and 5,573 events. Baseline was taken after the new smoke; it demonstrates preservation
  across the full run/audit, not a claim about a pre-smoke backup.
- Blind export **60 A / 12 independent-overlap B assignments**; repeated export on identical input produced
  byte-identical independently shuffled packets. All three source notices remain attached. Model/version/run
  fields and reviewer judgments are absent from item displays; answer text is retained unchanged. Empty A/B
  templates imported and rescored with **0 completed labels**, **0 valid paired samples**, null agreement/kappa
  and NOT_RUN. Assigned overlap denominator remains 12/excluded 12. Expected-answer, expected-abstention and
  contextual planned denominators are **45 / 15 / 40**. Failure census is empty for the successful Mock.

Environment was checked before startup: existing stopped project/container and pinned image, compose path,
127.0.0.1:25841, sole volume consumer, 0.5 CPU / 384 MiB limits, ~13 GiB available RAM and ~44 GiB free disk.
Only that container was started; new synthetic owner 811009/fresh runs were used. It was stopped afterward,
preserving the volume. No services outside this project were changed. The Python socket fence and explicit
Mock-only transport were used throughout execution. Fence counters do not observe libpq's C-level connections;
they are not a host-wide egress measurement. PG access was verified separately above.

## Versions, failures and artifacts

The successful smoke/full Mock ran code **`035aa9c56b473a391bcb6fe899aa5507b85f3a4f`**.
Final 44-test run and saved-packet rescoring ran **`40569c6fdd00737ac7bd6ba6e24d9358bced1d09`**.
The difference is limited to `public_review.py` and `test_public.py`: retaining assigned overlap counts when
labels are absent, with a regression assertion and explicit NOT_RUN status. Dataset, execution driver and
imported runtime are identical, so no repeated full run was needed. The final documentation commit only adds
this report, verification manifest and a README clarification of the Python fence; no executable/data change.

The first smoke at `af1632f` failed during summary creation: nullable successful-review error fields were used
in a numeric sum. Fixed by explicit boolean conversion in `035aa9c`. Its four raw turns, calls, accounting and
ledger remain at `.data/tutor-public-v1/pubv1-smoke-20261107`; no summary was produced and it is not called a
successful trial. Later smoke uses a fresh directory. A one-off audit was attempted before full aggregation
finished and stopped on a missing file; rerun after supervisor completion succeeded. An audit-only lookup used
`kappa` instead of inherited `cohen_kappa`; saved scores were subsequently checked with the correct field.
Neither audit issue changed source data or raw Mock results. All such directories remain intact.

Main local artifacts, rooted at `.data/tutor-public-v1/`:

- `pubv1-full-20261107/`: config, expected/actual raw turns, per-course calls/PG-mirrored ledgers/accounting,
  mechanical summary, diagnostic failure census and unannotated scores.
- `pubv1-smoke-r2-20261107/`: selected development-session smoke.
- `independent-full.json`, `independent-smoke.json`, `baseline.json`, `independent_check.py`: independent
  source/record/PG recount, preserved-state hashes and inspectable audit logic.
- `blind-full-20261107/`, `blind-full-replay-20261107/`: packets/templates and 0600 private keys; imports are
  `blind-import-A-20261107.json` and `blind-import-B-20261107.json`.
- `blind-scores-r2-20261107.json`, `blind-verification.json`, `verify_saved_review.py`: final empty-label rescore
  and independent packet/count assertions; earlier scores remain retained separately.
- `environment-before.json` and `network-*` directories: isolation/resource and Python-fence evidence.

[verification.json](verification.json) binds exact source hashes, executed versions, counts, artifact paths and
artifact/supervisor hashes. Source and data are checked in; raw Mock/DB artifacts remain local ignored data.

## Remaining work and NOT_RUN

No blocker to this data-preparation deliverable. Subject-competent independent review of all 60 tasks remains
pending. Single-publisher introductory technical workshop prose, fictional teaching examples, English-only
text, short closed units and conservative negative questions limit representativeness. This set does not
validate video ingestion, broad course generalisation, retrieval quality, Tutor quality or learning outcomes.

**NOT_RUN:** real Tutor/reference citation accuracy/coverage/task quality, real reviewer, independent expert or
human labels, human/model agreement or kappa, real tokens/cost, learning effect and any paid trial. No current
provider price, balance, model selection or authorised money/call budget was checked or invented. Future real
execution requires separate authorisation and reviewed compatibility; this task ends at local commits.
