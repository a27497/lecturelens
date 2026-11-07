# v11 same-scope real Tutor retest — 2026-11-07

**Decision: do not directly expand to 60/320 turns or consume SQL holdout.** This one retest completed
and repaired response metadata is now available. Dtype and spreadsheet-risk answers improved, but the
index question still has a wrong primary expression and another answer adds an unverified table property.
A small fresh development diagnostic set is a reasonable next step after source/rubric review and new
scope/budget authorization. No next batch, fix, model substitution or rerun occurred.

This is **Codex nonblind source review of eight tuned development turns**, not independent human blind
review, a significance test, unseen-course generalization or evidence of learning effects.

## Authorization and execution

- Clean branch `codex/tutor-scale-preparation`, actual execution HEAD
  **`c1c7e52699dd7f5877599067a49c486c34d1657e`**. No implementation changed in this task.
- The user's final explicit confirmation authorized **40 total requests / USD 0.10 local ledger cap**,
  accepting the moving alias and supplier-bill limitation. Earlier ambiguous replies caused no real
  requests. Prior USD 0.70 authorization/balance was not reused; no account interface was queried.
- Explicit Agent `p8-tutor-grounded-v11-development`, candidate SHA-256
  `b7fe50df1854703cc05d4ad039dad3245cc62adc5d68c3af7b394f2407f0ec58`.
- Retest plan SHA-256 `59fb85627dc75145e851b2a902348274284b43e5bce8d709da722d2f179a1ac8`,
  binding original scope `27c3361d841412f950b9aac5ab08a0d14e40b4fb0bc60801be0c9d181e5180d7`.
  Dataset `tutor-public-v1`, lock `4645c31d7e3eff19aa534714613d3ead64c1a7fcefcccba463fdbe9ef77f4620`:
  Python `python-01` and spreadsheets `sheets-01`, four complete turns each. No SQL registered/executed.
- Requested API ID **`deepseek-flash`**, only `https://api.deepseek.com/chat/completions`;
  thinking disabled, temperature 0, maximum output 1,200 tokens/request. Reviewer off, concurrency one,
  SDK/transport/application transport retries zero; existing bounded controller repairs retained.
- A private, Mock-checked request observer saved unchanged request bytes; the frozen v11 recorder saved
  decoded metadata. Its source SHA and execution start/end are retained. No headers/credentials recorded.
- One supervised trial, **11:18:44–11:19:20 UTC**, supervisor elapsed 37.14 s, no timeout/cleanup error.
  No automatic continuation, budget top-up or quality-driven rerun.

Read AGENTS.md and retest/baseline contracts. Reverified the dedicated PG project/compose/image, sole
volume consumer, no dependencies, free loopback 25841, 0.5 CPU/384 MiB limits and adequate RAM/disk before
start. Used only the dedicated evaluation credential and synthetic evaluation owner/run namespace.
Exported PG evidence, then restored the container to **exited 0**, volume retained and port released.
No product defaults, CI, other workspace, production/student data, push, PR, merge or deployment changed.

## Execution and observed quality comparison

Baseline is the unchanged [first-real v10-r2 report](../tutor-first-real-v1/REPORT.md), execution code
`c41245b`. Its original labels, scores and raw evidence remain intact. Arithmetic and quoted source spans
were rechecked. No baseline correction was required.

| Unit | Baseline v10-r2 | Retest v11 |
| --- | ---: | ---: |
| Expected / executed / completed turns | 8 / 8 / 8 | 8 / 8 / 8 |
| Failed / missing / scorable / reviewed turns | 0 / 0 / 8 / 8 | 0 / 0 / 8 / 8 |
| Verified complete correct / scheduled turns | 4/8 | **6/8** |
| Known incorrect / uncertain full-answer judgments | 4 / 0 | **1 / 1** |
| Core frozen reference completeness | 5/8 | 7/8 |
| Expected abstention correctness | 2/2 | 2/2 |
| Context consistency on applicable follow-ups | 6/6 | 6/6 |
| Citation-supported claim–evidence pairs | 22/24 | **30/30** |
| Citation presence / citation-requiring assertions | 24/31 | **30/38** |
| Supported-citation coverage / required assertions | 22/31 | **30/38** |
| Expected-answer turns with full citation presence | 1/6 | 2/6 |
| Expected-answer turns with full supported coverage | 0/6 | 2/6 |
| Real HTTP requests / failed HTTP requests | 20 / 0 | **19 / 0** |
| Executed local searches / finish decisions | 11 / 9 | 10 / 9 |
| Rejected finish proposals / successful repairs | 1 / 1 | 1 / 1 |

Task review uses the same frozen requirements and checks material additions as well as requested points.
The new `sheets-01:3` extra is **unverified**, not proven false: its complete-answer judgment is explicitly
null/uncertain and never counted as a verified pass. All eight remain reviewed and in the denominator;
there is no misleading 6/7 success rate. Baseline citation uncertainty concerned an attached tabs quote
for an otherwise reasonable full-unit derivation; the new raw-only property is not established anywhere
in the scenario/unit. We preserve that distinction rather than changing the original baseline grade.

Citation inventory: baseline 34 substantive claims / 31 requiring citations; retest **39 / 38**. Scope
caveats are checked for truth but need no positive citation. Semantic repetitions are deduplicated.
Local citation attachment is required; a citation explicitly closing a displayed worked example can
cover its code and stated result. In Python 1/2, “This produces…”/“For this data the output…” explicitly
close those examples. The baseline repaired assignment had no such closing reference. Generic nearby
citations do not automatically support an ordinal mapping. Exact spans, source quotes and attachment
notes are retained for review. These are Codex annotation choices, not independently validated human gold.

All 30 attached pairs are supported, but **eight required assertions remain uncited**, including the index
mapping and unverified raw-only assertion. The new derived passages also change citation-ID granularity:
17 turn-level distinct IDs versus 21 in the baseline. Neither fewer IDs nor 30/30 support establishes full
answer quality. Context consistency checks entity/scenario retention separately from mathematical truth.

## Per-turn source review

Locations are original Markdown lines in frozen Python/spreadsheet materials under
`eval/tutor-public-v1/materials/`; full exact answer spans, member IDs, quotes and source URLs are in the
private Codex inventory. No question, reference, scoring rule or original answer was edited.

| Turn | Retest source finding | Comparison |
| --- | --- | --- |
| Python 1 | Import/load/assignment and array orientation are correct (31–46, 75–78, 90–106, 124–136). The import code lacks a local explicit citation. First finish was 1,652 characters; one repair yielded 1,477, with no citation removed and no false whole-unit scope assertion. | Previously false scope caveat is gone; core actions retained. Length repair still needed. |
| Python 2 | Correctly distinguishes container/dtype and now reports `float64`/floating-point (140–163). The cited passage contains the method, code and output. Display explanation is supported at 80–88. | Previous missing result and unsupported dtype-API citation are resolved in this answer. |
| Python 3 | Axes/dimensions supported (132–136, 165–179, 738–741). Main answer is still `data[30, 20]`; only a conditional ordinary-counting alternative gives `data[29, 19]`. The explicit ordinal passage 194–219 is absent from observations; a second search remains unused. | Frozen main-answer failure remains. The 31st/21st explanation is now internally correct, a partial qualification improvement. Patient-label wording remains a dataset caveat; no rubric relaxation. |
| Python 4 | Canonical refusal; no learner environment/version or compatibility observation supplied. | Correct abstention retained. |
| Sheets 1 | Both inconsistent-entry risk and recombination/manual-work risk are now cited (56–65); adding a column and header handling are grounded (67–75). Concrete survey-day redesign is reasonable but uncited. The physical-merge caveat is read in its local topic scope. | Missing risk resolved; a citation gap remains. |
| Sheets 2 | Rejects repeated headers and cites freeze alternative (67–75). Row-as-observation consequence uses the same bounded derivation standard as baseline (41–47, 69–71). | Previous freeze-header citation gap resolved. |
| Sheets 3 | Row association, four dates and mixed summary statistics are supported (39–54); date-column contrast is reasonable. It additionally says the consolidated table “keeps raw observations only.” Neither the scenario nor metadata guidance (301–320) establishes that property or excludes calculated columns. | Core reference complete, new unsupported extra: full-answer correctness uncertain. Several comparison assertions are uncited. No false property is silently accepted as correct. |
| Sheets 4 | Canonical refusal; actual workbook absent, no count inferred from an illustration. | Correct abstention retained. |

## Model identity, tokens and costs

All **19** calls captured valid numeric usage and explicit cache hit/miss detail, 19 distinct body response
IDs, one reported fingerprint and no metadata anomaly. Returned `model` was **`deepseek-flash` for 19/19**;
this is still an alias, not proof of an immutable backend version. Allowlisted request-ID headers were
absent, so their field remains null/UNKNOWN. Baseline actual model, fingerprint, IDs and cache detail
remain **UNKNOWN_CAPTURE_FAILED**; they are not backfilled from this run or public version documentation.

| Accounting unit | Baseline | Retest |
| --- | ---: | ---: |
| Provider input tokens | 58,565 | **68,787** |
| Provider output tokens | 3,618 | **3,652** |
| Provider total tokens | 62,183 | **72,439** |
| Provider cache hit / miss input tokens | UNKNOWN / UNKNOWN | **21,504 / 47,283** |
| Comparable local peak/no-cache calculation (USD) | 0.0219111 | **0.0250185** |
| Cache-aware rate calculation (USD) | UNKNOWN | **0.009348162** |
| Actual supplier invoice / account balance | UNKNOWN | UNKNOWN |

Reopened [official pricing](https://api-docs.deepseek.com/quick_start/pricing/) on **2026-11-07**:
Flash USD per million tokens, off-peak hit **0.003**, miss **0.15**, output **0.60**; peak miss/output
**0.30/1.20** match the frozen local reservation basis. The published rule makes Saturday fully off-peak.
All retest request timestamps are on UTC Saturday.

`(21,504 × 0.003 + 47,283 × 0.15 + 3,652 × 0.60) / 1,000,000 = USD 0.009348162`.

This combines provider usage with public rates; it is **not a verified supplier debit/invoice**. Taxes,
rounding and granted-credit deductions are unknown; no account interface was called. Actual cost saving
versus baseline is **not comparable**, because baseline cache detail is unavailable. We do not compare
the new discounted calculation to the old peak/no-cache calculation and call it a saving.

The local conservative basis increased **USD 0.0031074 (14.18%)**; its settled 25,018,500 nano-USD equals
the ledger. Largest prefix exposure, including the one in-flight reservation, was **USD 0.0305157**,
below this run's USD 0.10 cap. All 19 requests, including the rejected finish, are counted. Pending zero,
no blocked state, no refunds fabricated from unknown usage. The local bound remains distinct from an
unverified supplier bill cap. Unused request/budget capacity gives no authority to run another trial.

## Context growth and comparison limits

Input increased **10,222 tokens (17.45%)**, output **34 (0.94%)**, total **10,256 (16.49%)**, despite one
fewer request. Actual dispatched evidence text rose from 36,903 to 70,341 characters. Replaying just the
same ten new search queries offline through old/new authorities yields 28,698 versus 58,276 source
characters (2.03×). These character counts demonstrate larger context, not token attribution. Prompt/schema,
history, queries, repairs and generated answers also differ, so the total token change is not a causal
estimate of grouping alone. Raw matched-query and wire-size details are saved.

Python 1 reserved **62,925 of 64,000** runtime proxy units after its length repair. These are JSON-byte
reservation units plus output allowance, not provider tokens. Remaining headroom is small; longer answers
or another repair may fail closed. Do not increase the bound silently for future samples.

Only Agent prompt/context/telemetry, associated identity and run namespace changed from the baseline.
Same requested model/settings do not guarantee the same actual backend, and temperature zero does not
establish deterministic generation. Baseline backend identity is unavailable. This development set informed
tuning; observed improvements cannot establish generalization, statistical significance or learning gains.

## Verification, artifacts and next boundary

Executed no implementation tests unnecessarily: this task changes reports only. Existing chained candidate,
dataset and scope checks passed; request-observer Mock probe passed before dispatch. After execution,
annotation validation checked exact answer spans, every output citation, pair labels and source quotes.
An independent loop reproduced both metric inventories and all token/cost arithmetic.

Verified 19 unique requests/reservations; exact request SHA equals saved wire bytes and ledger SHA for
all 19. **38 PG events equal full JSONL contents**, not merely event counts. Every final ID belongs to
observed authorized evidence. Tutor bodies contain no authored references/rubrics/answerability labels.
Original baseline PG events/policy and **2,090 pre-existing tracked/raw files** remain unchanged.
The raw automatic runner summary is preserved with quality NOT_RUN; the Codex review is a separate
derived assessment, not a rewritten automatic pass. No original score correction was needed.

- Run: `.data/tutor-retest-v1/v11-real-20261107/` — config, expected scope, decoded call metadata, turns, proposals,
  partial records, mirrored ledger and untouched automatic summary.
- Audit: `.data/tutor-retest-v1/v11-audit-20261107/` — this run's authorization, price observation,
  observer/hash, exact wire requests, PG snapshot, Codex source inventory,
  independent recount, context comparison and immutable artifact hashes. Raw/private records stay out of Git.
- Supervisor: `.data/dev-checks/tutor-v11-real-retest-20261107/` — bounded execution and cleanup evidence.
- [SUMMARY.json](SUMMARY.json) — non-sensitive aggregate; delivery adds only this report and summary.

Before another paid phase: independently review the ordinal/label wording, define fresh development cases
for numeric mapping and unsupported additions, inspect their evidence reachability and length-budget
headroom, freeze a new scope, then separately confirm calls/USD amount. Prefer a small fresh development
diagnostic run to broad expansion while the index and grounding risks remain. No new set was authored,
no further fix applied and no SQL/next batch executed here.

**NOT_RUN:** independent human agreement/Cohen's kappa, automated reviewer (disabled), SQL holdout,
expanded evaluation and learning effects. Actual supplier invoice/balance, immutable backend version and
baseline cache-aware cost remain **UNKNOWN**.
