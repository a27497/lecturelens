# V18 one-shot three-turn real smoke

**FAIL.** The frozen acceptance requires all three positions to complete with all
necessary content and valid supported citations. The first position delivered no
answer; the other two were skipped after the first failure. Counts are **0 completed,
1 failed, 2 skipped, 0 missing**, from 3 scheduled /1 attempted position. This is not
three independently observed model mistakes. There are no published answers or
citation pairs from which to claim correctness/support percentages.

Exactly **one invocation /3 real `deepseek-flash` HTTP requests** ran. No retries,
reviewer, embedding calls, alternate run, prompt/config changes or full16 followed.
The grant is consumed and expired; unused request or fee headroom is not permission
to resume. The process exited0 after recording failure; that exit is not a PASS.

## Version, authorization and preflight

- Actual execution HEAD: **`39e1d7454dd5dfe055c9ab7697c88a631ed795e7`**.
- Candidate code: **`4db4f05cf834a8dd8db155e58565afefc88b2b4d`**; freeze commit `af80398`.
- Identity: **`p8-tutor-usable-v18-development`**; no default switch.
- Manifest: `eval/tutor-usability-v18-v1/candidate.json`, SHA-256
  `34ddb43cdab734b630bc58637cd1497b418ffca1b631414c9e490049502f4950`.
- Packet: `eval/tutor-usability-v18-v1/sample-candidate.json`, SHA-256
  `ade24dceaf2bf50421b88373b68ebb65ba776c0d83754cab350fc06f558ba60e`.
- Reference: unchanged `reference-review-pack.json`; all listed source hashes and
  five exact source positions were checked. No reference/scoring fields entered
  any of the three actual requests. No SQL/holdout or student data was used.
- Current user grant: one ordered three-turn smoke, max3 ordinary decisions plus1
  format repair/turn, max12 sends,4096 output tokens/send, US$0.30 local liability.
  The user expressly accepted alias movement and supplier-billing uncertainty.
- Preflight **PASS** before egress: clean exact HEAD,22 frozen file hashes and
  their code-commit blobs, parent/version fences, unchanged4096/1024 code-point
  counting, receipt/rate/policy alignment, single-use claim/output absence and
  isolated durable PG with fsync/synchronous_commit on. Established provisioned
  credential was internally injected without logging/persisting its value.
- Endpoint/config: `https://api.deepseek.com/chat/completions`, model
  `deepseek-flash`, temperature0, thinking disabled, required tools,
  parallel_tool_calls=false, concurrency1, transport retries0, reviewer disabled.
  All three responses reported the requested alias and HTTP200. Actual account
  availability was established only by these authorized calls; no paid probe or
  models/balance API request preceded them.

The unchanged entry is `scripts/dev/run_tutor_smoke_v18.py --mode live`. A private
orchestration wrapper handles only grants/environment/supervision, invokes that
CLI once and hashes its own bytes. It does not patch the runtime, provider,
prompt, parser or source. The wrapper, exact command/start/end, receipts and
preflight are retained privately. Supervised commands were:

```sh
python3 scripts/dev/run_check.py --name v18-preflight --output .data/tutor-v18-live-20261107/checks --timeout 120 -- agent-service/.venv/bin/python .data/tutor-v18-live-20261107/launch_once.py --preflight
python3 scripts/dev/run_check.py --name v18-real-once --output .data/tutor-v18-live-20261107/checks --timeout 180 -- agent-service/.venv/bin/python .data/tutor-v18-live-20261107/launch_once.py --execute-authorized-once
```

The real invocation took9.185s including orchestration. The runtime's20s turn,
64000 turn proxy and US$0.30 fee ceiling were not exhausted.

## Actual failure chain

1. Request1 selected a search; the provider returned two search tool calls despite
   parallel_tool_calls=false. The frozen parser executed only the first and counted
   the other as **one dropped parallel call**, without another HTTP request.
2. Request2 selected a second search. The two actual observations supplied11 distinct
   current-turn IDs. The correct original count/indentation passage was present.
3. Request3 proposed four finish blocks: three `source` blocks and one `explanation`.
   All4 IDs were real and observed, and the proposal passed structural/size schema.
   **All4 literal-source checks failed.** The three source texts compose prefixes,
   paraphrases and ellipses rather than contiguous exact excerpts. The explanation
   anchor removes Markdown link syntax/newline from the actual loop sentence.
4. The controller committed `TUTOR_SUPPORT_REPAIR_REQUIRED` with
   `SOURCE_SPAN_MISMATCH`. A support correction consumes an ordinary decision,
   not the separate prepaid format allowance. All3 ordinary decisions were already
   used, so the next reservation failed **before request4** with
   `V18_SMOKE_TURN_REQUEST_LIMIT`. No support repair was sent; no format repair was
   used. The frozen user-authorized limit was respected.
5. The first turn was marked failed with answer/evaluation NULL and empty citations;
   both dependent turns were skipped. No rejected candidate reached the frontend.

This is an observed model output-contract violation followed by the configured
bounded stop, not an HTTP, deadline, fee-cap, token-output or4096-character failure.
The model's reason for choosing that representation or omitting other content is
not established. No counterfactual corrected answer is scored or sent.

## Per-position and source-based review

Reviewer: **Codex, the same author of the candidate/questions/development tests**.
This is nonblind AI source review, not independent human blind assessment or an
independent AI cross-review. No paid reviewer or executable model-code sandbox
was invoked. Original source and every actual request/response/checkpoint were
read; raw files remain unchanged.

| Position | Execution / delivery | Correctness and citation support |
| --- | --- | --- |
| 1 — explanation/code/indexing | **FAIL**, no publication | The rejected draft explains why loops replace indexed prints and correctly traces the changed counter2→3→4. It omits the required full commented changed-example Python, inside/outside print comparison (including intermediate3/4), and names[0]=Ada /names[1]=Grace explanation. All4 IDs are observed, but0/4 literal anchors satisfy the declared contract. The draft's count claims also lack their correct locally bound citation. |
| 2 — withheld-answer indentation question | **SKIPPED** | Correctness, targeted guidance, citation support, over-refusal and Socratic leakage **NOT_RUN**; no model request or answer. |
| 3 — wrong reply correction/history feedback | **SKIPPED** | Correctness, citation support and cross-turn feedback coherence **NOT_RUN**; no model request or answer. |

The first turn's required-point assessment is diagnostic only; no draft is promoted
to a delivered answer:

- Loop repetition/scalability/maintenance reasoning is substantially present in the
  draft and generally follows source lines33–107 and134–154.
- The changed-example arithmetic2→3→4 is correct under the counter increment rule,
  but the parenthesis “length starts at2, not the course's3” is ambiguous/misleading
  about counter versus collection length. The original counter starts at0, with
  three names and final3 (lines187–217). A later draft sentence correctly states
  original0→3; that later statement does not make the earlier wording clear.
- No complete commented Ada/Grace program is provided, so its full code correctness
  cannot be accepted. Short inline snippets from the original lesson are not the
  requested changed program. Missing print-placement and names-index explanations
  fail necessary-point completeness regardless of the arithmetic.
- There is no model abstention. The controller rejects malformed declared exact
  excerpts/literal anchors, not a blanket semantic rule against paraphrasing.
  This trial does not demonstrate normal teaching usability or over-refusal safety.

### A03: real IDs do not prove support

The fourth block binds to `a8aba2c5…` (original lines119–149), a general odds/loop
passage. That passage supports “once per element” and the general loop form; it
does **not** contain the original length0 /Curie-Darwin-Turing /increment trace
that the same block describes. The correct count passage `4c5cfe65…`
(lines189–217) was actually retrieved but not attached to those claims. The learner's
explicit changed inputs support those premises; they do not make unrelated source
text support every asserted original-course fact.

Blocks1–3 are mostly faithful paraphrases/summary of their bound passages, but they
are declared `source`, prefix “Course:” and splice text/ellipses. Calling that a
verbatim source excerpt is invalid. Literal matching failure must not itself be
misreported as proof that every underlying fact is false.

The fourth block's intended anchor is semantically similar to the source sentence,
but its byte/character span is not literal because the original contains a Markdown
link and newline. The frozen validator correctly rejected it under the existing
contract; no normalization or new counting rule was introduced.

Thus this trial exposes **draft citation/claim binding and clarity problems**.
It does not reproduce a published false explanation with a valid literal anchor:
all anchors failed earlier and nothing was published. A03's broader ability to
reject false interpretations with valid anchors is **not demonstrated or closed**.
No correctness/support rate is inferred from4/4 observed IDs or from0 published
citation pairs. Source access, Socratic answer withholding and feedback effectiveness
remain unobserved for skipped positions.

## Length and resource measurements

| Quantity | Actual |
| --- | ---: |
| Published answer / feedback length |NULL /NULL — no answer, not a zero-length success|
| Rejected block text lengths |230 /228 /209 /729 Unicode code points|
| Sum of rejected block text |1396 code points|
| Rejected candidate through unchanged renderer |**1770 code points** including labels, separators and full IDs|
| Rejected candidate feedback |0 code points (no feedback blocks required on first turn)|
| Finish arguments JSON string |2050 code points|
| Distinct proposed IDs |4, all observed|
| Actual output tokens by request |88 /46 /681, all below4096; finish_reason=tool_calls|
| Actual request entity bytes |3219 /14210 /17108, all below65536|
| Actual response entity bytes |893 /705 /2758, complete captures, all below131072|
| Runtime cumulative reserved proxy |47010, below64000|

1770 is a **renderer-only diagnostic of an unpublished proposal**, not a stored or
successful answer. No trimming, short-ID conversion, necessary-point deletion,
rewriting or alternate generation was performed. These observations do not prove
the new maximum is sufficient for every real teaching task.

## Usage, local ledger and rate estimate

All3 requests have known provider-reported usage. PG and JSONL contain the same
6 events (3 reservations /3 settlements), pending0 and no unknown usage. Runtime
failure still includes all three request costs; no failed-turn refund is assumed.

| Request / action | Input | Cache hit /miss | Output | Total | Local settlement USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 /search (one extra returned tool call dropped) |855|0 /855|88|943|0.000362100|
| 2 /second search |4452|384 /4068|46|4498|0.001390800|
| 3 /rejected finish |5393|384 /5009|681|6074|0.002435100|
| **Total** |**10700**|**768 /9932**|**815**|**11515**|**0.004188000**|

The frozen ledger uses no-cache peak300 input /1200 output nano-USD per token.
Final known local settlement is **4188000 nano-USD =US$0.004188**. Maximum
simultaneous reserved-plus-settled exposure was **11800500 nano-USD =US$0.0118005**,
below US$0.30. Gross reservations across time total25106700 nano-USD; that is not
simultaneous exposure or the final bill. Persistent runtime proxy reservations
are a separate resource counter and are not refunded into another run.

The [current official rates](https://api-docs.deepseek.com/quick_start/pricing/)
were rechecked before execution. It ran on a Saturday UTC, so the documented
weekend/off-peak rates apply: cache hit US$0.003/M, miss US$0.15/M, output US$0.60/M.
Using the reported cache split gives a separate rate-based estimate:
`(768*0.003 +9932*0.15 +815*0.60)/1000000 = US$0.001981104`.
This estimate does not modify the conservative local ledger.
**Supplier actual debit/invoice remains UNKNOWN**, was not queried, and is not
established by either figure. Alias movement and supplier-billing uncertainty
remain as explicitly accepted in this authorization. This is not cost-optimization
evidence and makes no saving claim.

## Evidence, record caveats and cleanup

Private raw root: **`.data/tutor-v18-live-20261107/`**; actual run **`run/`**.
[RESULTS.json](RESULTS.json) contains derived verdict, per-position review, usage,
limits, reconciliation and cleanup. [EVIDENCE_MANIFEST.json](EVIDENCE_MANIFEST.json)
is a hash-only index of32 private artifacts plus the one-use claim. Raw requests,
responses and DB state remain private/outside Git.

Retained evidence includes authorization/pricing/preflight and start/end records;
`run/execution.json`, `owner.json`, `summary.json`, `outcomes.json`, `runtime.json`,
`calls.jsonl`, `ledger.jsonl`; all3 `wire/*-request.body`, `*-response.body` and
capture metadata; read-only response/source analysis and ledger reconciliation;
process logs, PG custom backup and durable PGDATA. The captures are decoded HTTP
entity bytes before JSON parsing, **not reconstructed response envelopes or TLS
frames**. Known authorization strings are redacted, no headers/exception bodies
are published, and capture files are0600/private. Metadata reports complete
captures; no arbitrary secret or PII detector is claimed.

Two frozen record quirks are retained rather than “fixed” in place: the CLI exits0
for a recorded runtime failure; inherited verify-state fields still say
`ready_for_live=false`, list receipt categories and `real_calls=0` in the raw
summary/execution candidate object. These are preflight boilerplate, not actual
request totals or proof that admission was skipped. The successful admission,
3 captured live wire pairs,3 ledger calls and `real_model_calls=3` establish the
actual execution. This report does not treat those stale fields as a zero-cost run.

Only the owned temporary container was stopped/removed. Its live schema
`v18_diag_ead5dbb081ff4f659e9cafb852ca8502` was **not dropped**: durable PGDATA and
`state.pgcustom` backup remain privately available for reconciliation, with the
backup hash recorded. Port25841 is closed; all23 original running containers
remain. The durable used-grant claim is retained. No original service, credentials,
product code, default identity, frozen sample/reference/result, CI or deployment
was changed. The final local report commit is resolvable with
`git log -1 --format=%H -- eval/tutor-v18-smoke-v1/REPORT.md`; actual execution HEAD
above is intentionally different from that later documentation-only commit.

**Do not proceed to full16 or retry this smoke.** Completion, citation support,
Socratic guidance and cross-turn feedback gates have not passed. This one-shot
failure provides a bounded diagnostic, not quality acceptance or a measured
improvement. Cost optimization, independent human agreement, SQL holdout,
expansion, learning effects and quality-improvement comparisons remain **NOT_RUN**.
Execution and authorization have ended; wait for the user's next decision.
