# V18 bounded teaching contract

Candidate: `p8-tutor-usable-v18-development`. Opt-in only, default unchanged.
This is a new development protocol, not a rescore or improvement under v17.

## Publication and limits

| Layer | V17 | V18 | Unit / behavior |
| --- | --- | --- | --- |
| Published answer |1600|4096|Python `len`, Unicode code points, including every label/newline/full canonical citation|
| Published feedback |500|1024|Same counting; two feedback blocks max|
| Answer block |300|900|Four blocks max; source, explanation, checked calculation|
| Feedback text |exact learner/source comparison only|384|Two source/learner-anchored explanatory comparisons|
| Provider output |1200|4096|Tokens for the **entire tool response**, not visible-answer characters|
| Runtime reservation |UTF-8 serialized messages/schemas bytes +1200|same bytes +4096|Conservative proxy, not measured tokenizer usage or dollars|
| Runtime turn/session |64000/640000;4 ordinary+1 prepaid format;60/session|unchanged|Persistent resource proxies/call ceilings;20s turn unchanged|
| Smoke turn/run |not applicable|3 ordinary+1 prepaid format;12/run|Support correction consumes ordinary slots; no retry/expansion|
| Request/response wire |65536/131072|unchanged|Bytes; decoded entity body,20s request maximum|
| Citations |4 distinct IDs, full64-char IDs|unchanged|Current-turn observations, authority re-read before repair/publication|
| Source read |8 rows;8000/row,16000/batch;32768 bytes/batch|unchanged|Complete-v1; Java string limits UTF-16, Python code points; reject capacity, no prefixes|

The original1600/500 contract appears at initial Tutor commit `2690273`, with
later evaluations retaining it for comparability. No inspected UI or product
requirement establishes1600 as an answer display limit. Java's2000 and the
browser textarea's2000 limit learner input (UTF-16); Python input2000 counts
code points. Those input limits and their conservative mismatch are unchanged.
PG stores answer/evaluation as `text`, Java forwards JSON without a response
substring, and Vue escapes/render-wraps complete strings. The Tutor route returns
saved states and the panel polls; **there is no token-stream answer publication**.
Only a validated completed turn publishes, atomically with citations/checkpoint.

## Capacity basis

The retained v14 parsed failures are1982→1799 and1818→1633 characters, with594
and660 citation-marker characters. They already used only3–4 distinct IDs.
Counting just prose would hide real delivery cost; short IDs are not necessary
for this candidate. All old FAIL and original wire requests remain unchanged.
The measurement is reconstructed from retained parsed proposals, not original
response bytes, new generation, new scoring or proof of answer correctness.

A normal four-part explanation with a counter variation, complete commented
code, indentation reasoning and indexing uses **2721 rendered characters**, with
block lengths598/572/552/610 before citations/labels. A900 block ceiling gives
room for a longer code/example unit without requiring an arbitrary split at300.
Four maximum900-character explanation blocks, full64-character IDs and all
render labels/separators total **3989**, fitting4096. Two384-character feedback
blocks total **950**, fitting1024. ASCII/CJK/emoji/newline cases preserve the
same code-point accounting. There is no normalization, slicing or content deletion.

The measured complete teaching tool-argument shape is 3025 UTF-8 bytes (including
anchors, keys and full IDs). The4096-token output allowance budgets beyond that
representative envelope even under a conservative near-one-token-per-byte planning
estimate; this is not a tokenizer bound. It accommodates JSON framing, anchors, explanations,
code and feedback beyond the old1200-token cap. It is a **bounded engineering
allowance**, not a tokenizer measurement or guarantee that every legal maximum
Unicode proposal fits. Exact tokenization, real generation compliance and latency
remain NOT_RUN. The128KiB response,20s deadline and cumulative runtime caps can
still stop a call. Lowering token output after measuring real smoke usage is a
later decision, not an automatic tuning loop. Every reservation, including repair,
uses the new output allowance; format and support correction do not gain extra
resource budgets.

## Normal teaching versus guarantees

`source` is an exact contiguous attribution, not a semantic truth proof.
`calculation` retains v17's complete-expression positive grammar and bounded pure
value interpreter: comments/prose/controls cannot bypass it. It proves a selected
value, not relevance or execution of course code.

`explanation` permits bounded non-verbatim explanations, commented code and
conditional reasoning with a literal source anchor. The response labels these
as model interpretations. Feedback binds an actual current learner span and a
literal source anchor, allowing a specific correction instead of only juxtaposed
quotes. A non-verbatim sentence is not rejected merely for being a paraphrase.
**Anchor membership does not prove entailment.** An invented claim paired with a
real anchor can publish here; the retained negative case is a semantic defect/risk,
not a quality pass or a closed A03. The opt-in usability tradeoff deliberately
gives up v17's extract-only restriction; it must not be described as preserving
v17's deterministic prohibition on arbitrary explanation text. Unsupported claims,
wrong code or invented execution/mastery still fail the product quality rubric.
No lexical blacklist or synthetic semantic-score threshold is presented as proof.

Socratic output continues to accept only finite controller-owned, model-selected
hint acts, with no model free-text/answer/feedback channel. `locate_body` and
`trace_index` add general teaching questions without a supplied solution or
question-specific numeric answer. A03 interpretation risks do **not** reopen this
Socratic channel. Hint relevance/pedagogy remains judgment; full cited sources
can still contain solutions. There is no all-purpose semantic or pedagogical guarantee.

All observed-ID, ownership/revision/deletion, literal-anchor, learner-span,
canonical-binding, cancellation/accounting, persistent-budget, idempotency and
exclusive-schema checks remain. No database migration, public gateway schema,
frontend behavior, historical identity or default registration changes.
