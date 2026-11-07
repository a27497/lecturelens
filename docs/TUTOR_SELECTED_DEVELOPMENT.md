# Selected-source Tutor development identity

`p8-tutor-selected-v19-development` is an opt-in experimental Tutor identity.
`lecturelens_real_eval.tutor.selection_app:create_app` is Mock-only. Product
defaults and all previous identities remain unchanged. Java retains authenticated
Evidence authority; Python owns orchestration, context, execution and publication.

The model selects an observed Evidence ID and an inclusive interval of numbered
raw source units. Units contain at most200 Unicode code points and concatenate
losslessly to the complete authorized text, including Markdown, indentation,
comments, indexing brackets and long lines. The controller extracts quotations,
checks the observed source hash on re-read and final publication, and persists
source/span hashes plus code-point offsets. Source blocks cannot supply free text.
Explanations and teaching code remain generated text with selected support.

Three ordinary decisions and one **shared** finish correction permit at most four
sends per turn. A format or span/support error consumes the same durable correction;
a second error stops. Correction is finish-only, reserved before dispatch, and still
subject to cancellation, revision, deadline, token, wire and session fences. A
prepaid correction survives restart without another reservation. There is no retry.

Complete source and history remain in context. Compact JSON and mode-specific
schemas remove redundant protocol text; ordered search-result indices refer to
the full Evidence catalog instead of repeating IDs. The reservation formula remains
serialized UTF-8 message/schema bytes plus4096; this is a conservative proxy, not
measured tokenizer usage. Final body4096/evaluation1024 code points include all
rendered labels and full citation IDs. Block, anchor, request and response caps
remain bounded as specified in the versioned contract. Nothing is truncated.

Selection proves exact attribution, **not semantic entailment**. A true source
anchor can accompany a false explanation. A retained A03 negative case demonstrates
this residual defect. Code correctness, completeness, relevance and appropriate
teaching still require reviewing actual outputs. Socratic output remains finite
hint acts; relevance and all possible semantic leakage are not proved. Authored
offline teaching fixtures verify delivery capacity, not model intelligence.

See `eval/tutor-selection-v19-v1/CONTRACT.md` and `SMOKE_PLAN.md`. The explicit smoke
entry defaults to verification and requires new, exact one-use paid approval before
live dispatch. No real quality acceptance, independent human review, SQL holdout,
learning effects, release or scale authorization follows from these mechanism checks.
