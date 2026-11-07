# Fresh development Tutor batch v1

Frozen **v11-development**, new tasks only: two complete conversations per existing
Python/spreadsheet development course, **4 sessions / 16 turns** (8 per course;
lengths 5, 3, 3, 5 in execution order). No SQL holdout material/questions or candidate
results are loaded. This is new development on already seen units, not a fresh
course holdout. No model quality result exists for this batch.

## Data and source review

- `candidate-freeze.json` and `sources.json` were committed before new question
  authoring (`d1971c3`); original source bytes and licenses remain at
  `eval/tutor-public-v1/materials/`, with hashes, original/pinned URLs and dates in
  this batch's source manifest. Source-manifest `dialogue_ids` describe legacy
  provenance only; the new execution scope is solely `batch-plan.json` / part plans.
- Existing English Carpentries **Programming with Python / Analyzing Patient Data**
  and **Data Organization in Spreadsheets for Ecologists / Formatting problems**
  units are reused in full. No new downloads, linked data files, images or private
  material. Instructional content: CC BY 4.0; software examples: MIT. Preserve the
  original per-course LICENSE notices. Copyright (c) The Carpentries and lesson
  contributors; metadata passage also credits Research Data MANTRA, EDINA and
  University of Edinburgh (CC BY 4.0). No endorsement. Segmentation and newly
  authored questions/references are attributed adaptations; new text is CC BY 4.0.
- `questions.json` is the concise authored form; `development.json` adds exact
  original Markdown line quotations, pinned locations, answerability, dependencies,
  reference points, reasonable alternatives and rubric. `snapshot.json` has only
  the two course texts/provenance. 0/0 milliseconds are compatibility placeholders,
  never invented video times/pages.
- `CONTENT_REVIEW.json` records all **16** Codex source reviews, substantive novelty,
  overlap with the old 40 development tasks and source caveats. This is not
  independent human expert annotation. Entire units were available before; new
  referenced lines do not prove they were unseen by an earlier model.
- New emphases: negative string endpoints, short suffixes, documentation discovery,
  no-argument calls/multiple assignment, pasted-text export risks, overloaded NA
  clarification, and compatibility versus recommendation. Indexing, null/metadata
  principles and generic abstention skills overlap earlier tasks. These are not
  renamed patient-index questions or changed-number variants.
- **12 answerable / 4 insufficient**, 10 semantic follow-up turns. Ordinary tasks
  accompany boundary/false-premise/unsupported-extension cases. All are ordinary
  Tutor mode; no reviewer or Socratic-mode comparison is added.

`grading-rules.json` freezes a small-sample engineering gate before candidate
execution: 16 completed and reviewed, no failure/missing; complete correct ≥14/16
and ≥7/8 each course; critical index/slice 3/3; clean expected refusals 4/4; explicit
clarification 1/1; semantic context ≥9/10; supported citation pairs ≥0.95, supported
claim coverage ≥0.90, and fully supported expected-answer turns ≥10/12. All
requirements apply together. These are risk tolerances, not significance or
unseen-course claims. Material uncertain additions are not confirmed passes;
missing annotations block a decision. Pair-level accuracy is always accompanied
by claim coverage and all planned-turn denominators. See exact units, denominators,
uncertainty/missing/refusal treatment and rationale in that file.

## Existing runner, fixed parts and safety

The unchanged `tutor-repair-v1/repair_run.py` is fixed to eight turns and 40 calls.
The thin `batch_run.py` runs **two predefined parts**, each containing one complete
session from each course, with explicit `GroundedTutorRuntime`, original v11 prompt,
passage selection, channel, metadata recorder, persistent store and ledger. No
product behavior, old manifest, hash, dataset or result is changed. The new wrapper
is not an Agent identity change; it is pinned in `freeze-lock.json` separately.

`bridge.py` extracts five pinned pure utility functions from the original public
loader because that module eagerly imports mixed development/SQL authoring. It
never executes that authoring import or the old selector. A process file-audit
fence rejects mixed snapshot/authoring, SQL question/material reads. Historical
candidate verification still hashes its pinned input files; no historical data
projection or candidate trial is run. New material projection uses the identical
block IDs from the two permitted source files only.

Each part has an independent inherited ledger with **preallocated** half of the
explicit total call and nano-USD caps (remainder goes to B). The sum cannot exceed
the explicit totals. Unused part allowance is not transferred. Stop the whole batch
on the first incomplete part; the other expected turns stay failed/missing rather
than changing the sample. Different run names are globally single-use. No resume,
model fallback, top-up or automatic rerun. The inherited local reservation limit is
not a supplier bill guarantee. Both parts enforce reviewer off before lookup/send.

Default is preparation only: no DB/transport or provider credential lookup.

```bash
PYTHONPATH=agent-service/src agent-service/.venv/bin/python \
  eval/tutor-fresh-dev-v1/batch_run.py \
  --agent p8-tutor-grounded-v11-development --model deepseek-flash
```

After checking the dedicated **stopped** evaluation PG instance's compose path,
port 25841, exclusive volume consumer/dependencies and limits (0.5 CPU/384 MiB),
start only that container. No Java/MySQL/browser stack is needed. Run a new name:

```bash
docker start lecturelens-tutor-scale-prep-20261107-postgres-1
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py \
  .data/tutor-fresh-dev-v1-20261107/network-NEW \
  eval/tutor-fresh-dev-v1/batch_run.py --mock \
  --agent p8-tutor-grounded-v11-development --model deepseek-flash \
  --reviewer off --concurrency 1 --max-calls 80 --max-usd 0.70 \
  --output .data/tutor-fresh-dev-v1-20261107/mock-NEW
docker stop lecturelens-tutor-scale-prep-20261107-postgres-1
```

The amounts/tokens above are **non-billable Mock fixtures**, not approved real
spending. The safe launcher strips provider/proxy environment and fences Python
sockets to the dedicated PG. Default preparation does not need a running database.
Use the existing `scripts/dev/run_check.py` for bounded execution. Keep the volume
and raw evidence, including unsuccessful trials. Do not touch unrelated services.

`expected-turns.json` precedes calls. Global/part configs bind code SHA, scope/data/
candidate/adapter hashes and budget allocations. Per-part `calls.jsonl`,
`ledger.jsonl`, raw/partial turns and aggregate `turns.jsonl` preserve original
outputs, metadata, repairs, failure causes and all 16 denominators.
`failure-review.json` is a diagnostic census, not a random quality sample.
`unannotated-scores.json` reuses v2 scoring: empty labels remain NOT_RUN, with null
ratios/kappa. The existing Mock oracle uses expected-negative membership to test
protocol only; its correct refusals are not real quality evidence. References and
rubrics never enter candidate requests; published worked solutions are legitimate
source content, not hidden new evaluation labels.

Validation: `python data.py` checks exact hashes, projection, source quotations,
complete scope and counts; `--build` is exclusive creation for an empty scratch
copy of the authoring inputs/tools, not permission to replace this version.
`test_batch.py` checks scope/hash rejection, source locations, isolation, default/
live gates, missing/failure arithmetic and question/reference separation.

See [EXECUTION_SHEET.md](EXECUTION_SHEET.md) for the unapproved future real-run
proposal and [REPORT.md](REPORT.md) for actual Mock verification. After freezing,
review outcomes without changing this dataset, candidate or gate; any later change
requires a distinct version and preserved results.
