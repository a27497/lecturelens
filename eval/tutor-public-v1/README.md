# Public-course Tutor evaluation set v1

Provisional **Codex-authored and Codex-reviewed** questions over genuine published teaching units.
No independent human expert labels or real-model results. Synthetic suites remain unchanged regression fixtures.

## Sources and licenses

| Split | Published course | Complete textual unit | Sessions / turns |
| --- | --- | --- | --- |
| Development | [Programming with Python](https://swcarpentry.github.io/python-novice-inflammation/) | [Analyzing Patient Data](https://swcarpentry.github.io/python-novice-inflammation/02-numpy.html) | 4 / 20 |
| Development | [Data Organization in Spreadsheets for Ecologists](https://datacarpentry.github.io/spreadsheet-ecology-lesson/) | [Formatting problems](https://datacarpentry.github.io/spreadsheet-ecology-lesson/02-common-mistakes.html) | 4 / 20 |
| Holdout | [Databases and SQL](https://swcarpentry.github.io/sql-novice-survey/) | [Filtering](https://swcarpentry.github.io/sql-novice-survey/03-filter.html) | 4 / 20 |

All material and questions are English. These are established research-computing workshop courses. Each scope is
one continuous, complete textual episode, including its published examples/solutions; other episodes, linked
images, data files and video are not included. Original Markdown retains links to omitted assets. Questions
require only retained prose/code; the spreadsheet discussion reference's necessary scenarios are supplied in questions.

[sources.json](sources.json) records course/original/pinned URLs, upstream revisions, acquisition date, byte
counts, hashes, authors, license evidence and attribution. `materials/` retains each unmodified source Markdown
and its same-revision LICENSE.md. Each lesson's license page and pinned license were checked: instructional
material is **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**; software examples use **MIT** with
permission notices retained in the attached license files. Credit: Copyright (c)
[The Carpentries](https://carpentries.org/) and lesson contributors. Evidence segmentation, questions and
references are attributed adaptations; new question/reference contributions are also CC BY 4.0. No endorsement.

The spreadsheet metadata prose additionally credits **Research Data MANTRA**, EDINA and Data Library /
Research Data Service, University of Edinburgh ([original](https://mantra.ed.ac.uk/),
[CC BY 4.0 confirmation](https://mantra.ed.ac.uk/acknowledgements.html)). Its source attribution is retained
at original line 326. Other linked publications are references only; their destination content is not copied.
No external images/logos/media/data were downloaded. Preserve all notices when redistributing adaptations.

Re-fetching requires only unauthenticated HTTPS GET of each manifest `download_url` and `license_evidence_url`,
then SHA-256 comparison. Stop on any difference. No account/token is needed. Mock execution does not fetch sources.

## Split, units and references

The course/session split was committed **before question authoring or adapter debugging**, in `31acd91`.
`course-split.json` SHA-256: `1eea49193925d5565bae62ce611d79871a1b78ad450c494b344ac4456bed9a3c`.
The entire SQL course is evaluation-only: its materials, questions, references and eventual results must not
feed product/prompt tuning. This is a procedural repository boundary, not an access-control secret. Codex saw
the holdout to author/audit this set and verify compatibility; no Tutor prompt/runtime was tuned. Base-model
exposure to these public courses is unknown. Preserve the first real holdout trial and all failures; a later
tuned candidate needs a fresh course holdout.

`development.json`: **2 courses / 8 sessions / 40 turns**. `holdout.json`: **1 / 4 / 20**.
Total **3 / 12 / 60**. A course is one published course identity with a closed textual unit. A session is an
independent complete conversation; a turn is one learner message plus its scheduled Tutor result, including
failures/missing. Requests/events are not turns. Session lengths are 4–6; all twelve category sequences differ.
There are **45 answerable**, **10 insufficient-evidence**, **5 outside-unit** turns; **12 false-premise** turns
are among the answerable tasks. Follow-ups test referents, dimensions, conditions, repair and recovery.

Each turn records task type, supplied-unit answerability, dependencies, reference points, reasonable answer
boundary, exact source-line quotes, supporting/refuting evidence and rubric. Negative references are nearest
scope anchors, not proof of global absence; separate insufficiency reasons follow whole-unit content review.
“Course” scope means the supplied unit, not all external episodes. `snapshot.json` holds source text/provenance,
never new reference answers or grading rubrics. Tutor requests receive learner text, mode, conversation and
retrieved course evidence; reference, refusal, split and dependency labels stay outside that boundary.
Published worked solutions are instructional evidence, distinct from the newly authored evaluation references.

Immutable GitHub links and original Markdown line numbers are authoritative. Legacy `DOCUMENT_PAGE` and 0/0
millisecond fields are compatibility placeholders, **not video timestamps or PDF page numbers**. The inherited
authority uses deterministic lexical retrieval, with no embedding calls; this task does not validate retrieval quality.

`public_dataset.py` verifies source/license/split/projection hashes, reference quotes, IDs, dependencies and
course isolation. To reproduce projection bytes, copy authoring inputs and `materials/` into an empty scratch
directory and run `python public_dataset.py --build` there. Exclusive creation refuses existing outputs.
Never replace this version after a real trial. See [CONTENT_REVIEW.md](CONTENT_REVIEW.md).

## Mock compatibility

Existing entry points fix synthetic scope/counts. These evaluation-only adapters supply the new dataset and
complete-session selection while reusing frozen TutorRuntime/Store, SnapshotAuthority, TutorProvider,
MockTransport, RecordedChannel, persistent budget ledger, citation validation, annotation import and v2 scoring.
No product runtime, old dataset, identity, blind sample or result changes. **No --live switch exists here.**
Both the socket-fence guard and inherited channel MockTransport admission are required. A future real adapter
needs separate review/authorization and confirmed models/call/money budgets; old live commands cannot run this set.

Before starting the existing DB, verify project/compose path, image, loopback 25841, volume/sole consumer,
free port and resources. This task uses fresh runs/sessions, synthetic owner **811009**, dedicated tutor_scale
role/database and the existing container's 0.5 CPU / 384 MiB limits. No browser account, private student/patient
data, Java or MySQL. Only start/stop this verified container; retain its volume.

```bash
python3 eval/tutor-public-v1/public_dataset.py
# Only after verifying the stopped isolated container, volume and port:
docker start lecturelens-tutor-scale-prep-20261107-postgres-1
# Complete development session, selected by course AND session:
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py \
  .data/tutor-public-v1/network-smoke-NEW eval/tutor-public-v1/public_mock.py \
  --split development --course carpentries-python --session python-01 \
  --max-calls 24 --output .data/tutor-public-v1/smoke-NEW
# Full 60-turn mechanics check, with explicit holdout opt-in:
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py \
  .data/tutor-public-v1/network-full-NEW eval/tutor-public-v1/public_mock.py \
  --split all --evaluation-only-holdout --max-calls 240 \
  --output .data/tutor-public-v1/full-NEW
```

Run from repository root with fresh output/network names. `--split` is required. Repeat `--course`/`--session`
for exact IDs. Unknown, duplicate, empty or cross-split choices fail before ledger creation. No turn truncation,
budget-derived scope or full-suite fallback. The safe launcher strips provider/proxy/tracing environment and
blocks non-test egress. Longer checks can use the existing bounded supervisor documented in
[v2](../tutor-scale-v2/README.md).

The 3..240 total request ceiling is conservatively divided across selected courses. Each shard retains the
inherited 0.70 historical **Mock reservation** ceiling, not a price, spending authority or bill. Fake 120/80
tokens never become real consumption. Runtime token/call/deadline bounds remain unchanged. Expected turns
are saved before requests; config records code SHA, adapter hashes, data lock, scope and caps. Shard/aggregate
raw turns, calls, mirrored ledgers, accounting, explicit missing/failed denominators, diagnostic census and
unannotated task scores are retained. Incomplete execution exits 1. The inherited oracle Mock uses expected
negative membership solely to test protocol; it cannot establish semantic quality.

## Blind census and scoring

This small set uses a **census**, separate from the unchanged old random 100/20 design. A receives every
selected turn; B independently receives preregistered ordinal 2 in each selected session (12 at full scope,
4 per course). Shuffle seed is 20261109 + rater character code. Failure/missing results remain in the census
and separate diagnostic list, never become completed semantic annotations or replace random quality samples.

```bash
agent-service/.venv/bin/python eval/tutor-public-v1/public_review.py export \
  --run .data/tutor-public-v1/full-NEW --output .data/tutor-public-v1/blind-NEW
agent-service/.venv/bin/python eval/tutor-public-v1/public_review.py import \
  --key .data/tutor-public-v1/blind-NEW/private-key.json \
  --packet .data/tutor-public-v1/blind-NEW/packet-A.json \
  --ratings .data/tutor-public-v1/blind-NEW/annotation-A.json \
  --output .data/tutor-public-v1/import-A-NEW.json
# Independently repeat for B, then:
agent-service/.venv/bin/python eval/tutor-public-v1/public_review.py score \
  --key .data/tutor-public-v1/blind-NEW/private-key.json \
  --imports .data/tutor-public-v1/import-A-NEW.json .data/tutor-public-v1/import-B-NEW.json \
  --output .data/tutor-public-v1/scores-NEW.json
```

Give each rater only their packet/template; keep the 0600 identity key private until independent submission.
Packets retain history, sources, references and license notices, hiding model/version/run identity and model
judgments. Public course names are legitimate context. Answers remain unchanged; self-identifying answer text
can compromise blinding and needs a recorded caveat. Imports bind exact packet/source hashes.

Scoring reuses [v2 definitions](../tutor-scale-v2/README.md): citation support over all annotated claim–citation
pairs, claim coverage over citation-requiring assertions, and expected-answer turn coverage retaining wrong
refusals, uncited answers, failed/missing executions. Reasonable refusal is separate from an unsupported
non-answer. Task/refusal/context metrics disclose applicable/planned, scorable, assessed and missing counts.
Context consistency needs semantic prior-turn review, never string equality. Agreement/kappa use valid paired
labels only. No labels/pairs means null ratios/kappa and NOT_RUN, never a pass. This Mock compatibility path
keeps real quality, human score status, tokens/cost and learning effect NOT_RUN.

## Limits

Three introductory research-computing/data courses from one publisher do not represent broad university
disciplines, Chinese teaching, noisy OCR/transcripts, video ingestion, long-document retrieval or learning gains.
Python uses an explicitly imaginary colleague and educational inflammation scenario; SQL uses fictional
expeditions. Those examples occur in genuine external teaching materials. No source data files were fetched.
Short unit-bounded negatives can favour conservative refusal; 60 turns do not establish generalisation or precision.
Codex authored and reviewed both sides: correlated errors remain possible. A subject-competent human should
review all 60 turns and source caveats before a real trial. Current provider prices, balances, models and
authorised call/money budgets remain UNKNOWN/unconfirmed. See [REPORT.md](REPORT.md) for executed evidence.
