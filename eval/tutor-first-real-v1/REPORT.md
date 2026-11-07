# First real frozen Tutor pilot — 2026-11-07

**Decision: do not expand evaluation yet.** The authorized eight-turn pilot completed, but source review
found a wrong Python element expression, incomplete answers/citations and a response-metadata evidence
gap. These eight introductory English text turns do not establish generalization or learning effects.
This is **Codex nonblind source review**, not independent human expert annotation or model-reviewer grading.
Retrieval here is the evaluation SnapshotAuthority's deterministic lexical path, not a measurement of
deployed embedding retrieval, ingestion, video/ASR or Chinese-course behavior.

## Authorization, identity and execution

Started at clean `c41245becb5e6f72494e5c045883da79bc7d1fbf`, branch `codex/tutor-scale-preparation`, in
`/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens`. Read AGENTS.md and the existing execution contract.
The initial replies approved intent but supplied no numeric amount; no model request was sent then.
The user subsequently explicitly accepted the moving-alias/billing limitations and replied **0.7** for the
USD cap. Applied **USD 0.70 local ledger cap / 40 total requests**, reviewer off, concurrency one, transport
retries zero, existing bounded controller repairs. No increase, alternate model, second trial or top-up.

- Executed Agent: `p8-tutor-python-notation-v10-development-r2`, explicitly instantiated by the existing
  `eval/tutor-pilot-v1/pilot_run.py`; product defaults remain unchanged.
- Candidate SHA-256: `8f430ba637bb13dfd415bf29d4785e116d44141d7d3c49946ede77cee45079cf`.
- Scope SHA-256: `27c3361d841412f950b9aac5ab08a0d14e40b4fb0bc60801be0c9d181e5180d7`.
- Data-lock SHA-256: `4645c31d7e3eff19aa534714613d3ead64c1a7fcefcccba463fdbe9ef77f4620`.
- Dataset `tutor-public-v1`: Python `python-01` + spreadsheets `sheets-01`, **4 + 4 complete turns**.
  No SQL course was registered/executed. Model requests contain no authored reference/rubric labels.
- Actual execution code version: **c41245b**. No tracked implementation/data file changed during this task.
  A retained one-shot transport tee recorded the unchanged request bytes/status/times; its SHA is in the
  execution-start artifact. It changes no model decisions/payloads and has no retry path.
- Requested API ID: **deepseek-flash**, only `https://api.deepseek.com/chat/completions`, thinking disabled,
  temperature zero, maximum 1,200 output tokens/request. The authenticated endpoint accepted all requests
  and returned parseable tool decisions. **Actual returned model/version: UNKNOWN, capture failed for 20/20.**
  The public-document version mapping is not substituted for missing response evidence.

Used only the verified dedicated evaluation PG: correct project/compose path, pinned image, free loopback
25841, sole volume consumer, no service dependencies, 0.5 CPU/384 MiB limits and adequate resources.
Consumed only the known private evaluation credential in the sender; no key/header or account data is in
committed results. The supervisor ran the one trial with a 240 s bound, no timeout/cleanup failure.
Requests occurred around **10:20:06–10:20:45 UTC**. Afterwards the dedicated container was restored to
**exited 0**, with its volume and live run/session/ledger records retained. No other service/worktree changed.

## Execution and accounting evidence

| Unit | Observed |
| --- | --- |
| Courses / sessions / expected turns | 2 / 2 / 8 |
| Executed / completed / failed / missing turns | 8 / 8 / 0 / 0 |
| Scorable / Codex-reviewed turns | 8 / 8 |
| Expected answers / expected abstentions | 6 / 2 |
| Real HTTP requests / HTTP 200 / failed requests | 20 / 20 / 0 |
| Local searches / finish decisions | 11 / 9 |
| Rejected finish proposals / successful bounded repairs | 1 / 1 |
| Transport retries / reviewer calls | 0 / 0 |
| Pending reservations / blocked ledger | 0 / none |
| Provider-reported input / output / total tokens | 58,565 / 3,618 / **62,183** |
| Missing usage records / missing returned-model records | 0 / **20** |

The 20 requests comprise the normal 16, three second-search decisions and **one format-repair request**.
`python-01:1` first proposed seven distinct citations; the controller rejected that finish and the next
model request produced four. The rejected proposal and its tokens remain counted. Mechanical completion
does not mean answer quality passed; the unmodified runner summary still has automatic quality NOT_RUN.

Independent recount verified eight unique exact scope keys; all 20 request-body SHAs match corresponding
ledger reservations. Exported **40 PG events equal the full 40 JSONL records**, not merely event counts;
the latest states are 20 settled calls. Call/turn/provider-usage totals reconcile. All 21 final turn-level
distinct citation IDs belong to observed authorized course evidence, which does not establish support.
Before/after SHA comparison confirms **546 existing related tracked files unchanged**.

## Per-turn source review

Locations are original lines in the frozen [Python material](../tutor-public-v1/materials/carpentries-python.md)
and [spreadsheet material](../tutor-public-v1/materials/carpentries-spreadsheets.md). Full exact answer spans,
attached IDs, source quotes and pair judgments are retained in the raw Codex inventory. Material attribution
and CC BY 4.0/MIT notices remain in [the original source manifest](../tutor-public-v1/sources.json).

| Turn | Codex finding and source basis | Disposition |
| --- | --- | --- |
| `python-01:1` | Import/load/assignment actions are present (31–40, 50–52, 90–99). Repair removed retention citations while keeping those claims; it added the false assertion that the unit covers nothing beyond loading/assignment, contradicted by slicing (238–260) and analysis (296–311). | Core requirements complete; strict correctness fails |
| `python-01:2` | Correctly distinguishes ndarray from element dtype (142–147), but omits the required `float64`/floating-point result (149–158). Its dtype API advice cites a block that does not actually name that API. | Partial, not a claim that dtype advice is false |
| `python-01:3` | Correct row/patient and column/day orientation (132–136, 173–179), but gives `data[30, 20]`; frozen reference and source 194–219 require `data[29, 19]`. Generic caption 240–244 supports selecting one element, not this ordinal conversion. Later everyday-counting explanation is also confused. | Incorrect frozen element expression |
| `python-01:4` | Clean canonical abstention: the unit contains no observation of the learner's installed NumPy or a laptop-specific compatibility guarantee. | Correct abstention |
| `sheets-01:1` | Combining/connections and single-table/date-column redesign are reasonable (58–67), but the required inconsistent-formatting risk in 62–65 is omitted. The redesign has no adjacent supporting citation. | Partial |
| `sheets-01:2` | Correctly rejects repeated headers (69–71) and recommends freezing them (73); the required freeze alternative is uncited. Other citations support the row/formatting explanation. | Correct task, citation gap |
| `sheets-01:3` | Correct row-association versus explicit date-column contrast (41–54, 67), with coherent prior-table context. The citation about recombining tabs (62–65) only uncertainly supports the analogous side-by-side-table claim. | Correct task, citation limitations |
| `sheets-01:4` | Correctly refuses an exact duplicate/misalignment count: no actual workbook is supplied, and an illustration cannot establish the team's count. | Correct abstention |

Dataset caveats are retained, not used to change grades: “patient 30” can suggest a zero-based label rather
than an ordinal, although the frozen reference/source specify the ordinal conversion. The dtype rubric is
more specific than merely rejecting the learner's inference. A future dataset revision should clarify these
with independent review; this trial is scored against the existing requirements, with partial credit visible.

## Metrics and denominators — Codex review only

- **Strict task correctness 4/8 (50%)**: all mandatory reference requirements and no materially false extra
  assertion. **Core reference completeness 5/8** separately credits the correct actions in `python-01:1`.
  No partial/incorrect output has been relabeled as a pass.
- **Expected abstention correctness 2/2**. Both actual abstentions are the two expected negative cases;
  none of the six expected-answer turns abstained.
- **Context consistency 6/6** applicable follow-ups: maintains the same array/table/scenario without
  contradicting earlier published answers. This does not reward the incorrect index or establish truth.
- Inventory: **34 distinct substantive assertions**, of which **31 require citations**. Three whole-unit
  scope/limitation assertions do not require positive citations but are still checked for truth (including
  the false scope assertion). Repeated semantic claims are deduplicated; explicit local citation attachment
  is used. These are transparent Codex annotation choices, not independently validated human gold.
- Citation support: **22/24 claim–evidence pairs (91.7%)**, with 1 unsupported and 1 uncertain pair.
  Uncertain remains in the denominator. This is not an all-answer accuracy score.
- Citation presence coverage: **24/31 required assertions (77.4%)**. Supported-citation coverage:
  **22/31 (71.0%)**. Uncited required assertions remain in these denominators.
- At whole expected-answer-turn level, full citation presence is **1/6** and full supported coverage **0/6**.
  Two reasonable refusals are not counted as uncited required answers; all eight remain in task counts.
  Failures/missing are zero in this run and were not removed to compute the denominators.

The existing annotation validator checks exact answer spans, all output citation IDs, complete pair labels
and exact supporting source quotes; the existing arithmetic helper is reused. An independent loop recounts
the 31/24/22 units. “ANNOTATED” in that helper means **Codex labels here**, not human annotation. There are
zero independent human or model-reviewer paired labels: human/model agreement and Cohen's kappa are NOT_RUN.

## Costs: reported usage, calculated fees, unknown invoice

Rechecked the [official pricing page](https://api-docs.deepseek.com/quick_start/pricing/) on 2026-11-07.
The current published Flash USD-per-million rates match the frozen Tutor ledger's conservative peak
cache-miss input/output basis. With the provider-reported usage above:

`(58,565 × 0.30 + 3,618 × 1.20) / 1,000,000 = USD 0.0219111`.

This exactly matches **21,911,100 nano-USD** in the settled local ledger. It is a rate-based conservative
calculation, **not the actual supplier bill**. All calls were on Saturday/off-peak under the published rule.
For illustration only, off-peak all-cache-miss yields USD 0.01095555; all-cache-hit yields USD 0.002346495.
Cache breakdown was not captured, so neither scenario is a measured bill or a guaranteed billing interval.
No account/billing interface was called; actual debits, invoice, tax/rounding and balance remain UNKNOWN.
Unused call/budget capacity grants no authority to run more trials.

## Defects, evidence limits and smallest follow-up conditions

1. **Answer/evidence selection:** dtype result and the explicit ordinal paragraph were absent from their
   retrieved windows. Blank-separated code/output blocks and lexical ranking are plausible contributors;
   the model also finished the index turn without its available second search. These observations do not
   isolate a single cause. Minimal future work: preserve adjacent prose/code/output context and require a
   targeted search or clarification for numeric mapping; evaluate as a new version without changing this run.
2. **Repair loses grounding:** the seven-to-four citation repair kept uncited retention instructions and
   added an incorrect scope caveat. Preserve task-critical evidence/claims during repair rather than merely
   satisfying count limits. This run was not patched or repeated. Legal brackets were retained; the index
   failure is semantic, not a recurrence of the old parentheses contract.
3. **Response-metadata evidence gap:** existing MetadataTransport and the run tee failed to parse every raw
   transport body, while Channel successfully parsed decoded content/usage. Offline identity/gzip streaming
   fixtures reproduce loss of model metadata before HTTPX content decoding. Actual Content-Encoding and
   encoded bodies were not retained, so exact production encoding/cause cannot be proven retrospectively.
   Actual model/fingerprint/cache detail must remain UNKNOWN, not filled from public documentation.
   Minimal fix: bounded decoded-response metadata capture, including failure paths/full numeric usage,
   validated with identity/compressed/streamed responses before separately authorized new execution.

The run-specific tee's initial pre-consumed Mock probe failed to create a response frame and was not a
successful instrumentation check. The authorized live run then executed once; streamed frames exist for
all 20 responses but do not recover the missing model fields. This evidence limitation is retained rather
than hidden or “fixed” with another paid call. Only offline diagnosis/arithmetic followed the real trial.

Before expansion: resolve these quality/metadata problems under new versioned evidence, clarify the noted
rubric wording through independent review, establish real response-model/usage provenance, then seek a
separate bounded rerun/expansion authorization. Do not automatically use 60/320 turns or the SQL holdout.

## Artifacts and NOT_RUN

- Original run: `.data/tutor-pilot-v1/first-real-20261107/` — configuration/SHAs, exact expected eight turns,
  answers/evidence/proposals, call records, immutable mirrored JSONL ledger and original summary.
- Audit: `.data/tutor-first-live-20261107/` — authorization, observer SHA/source, UTC wire events/request
  bodies/response frames, full scoped PG snapshot, Codex source labels, independent recount, offline
  metadata reproduction and artifact hashes. Raw/private evaluation records stay outside Git.
- Supervisor: `.data/dev-checks/tutor-first-real-20261107/` — bounded process result/times/cleanup evidence.
- [SUMMARY.json](SUMMARY.json) is a non-sensitive reviewed aggregate. Delivery changes only this report
  and that aggregate; execution code remains **c41245b**. No product/CI/frozen asset/result edits, push,
  PR, merge or deployment. The dedicated database is stopped with evidence retained.

**NOT_RUN:** independent human blind review/agreement/kappa, automated reviewer, learning effects,
expanded 60/320-turn evaluation, SQL candidate execution, load tests and deployment. Actual returned model
identity/cache detail and actual invoice are **UNKNOWN**, not zero and not claimed as verified results.
