# Selected-source Tutor development identity

This branch contains `phase1c-tutor-repair-development`, an opt-in offline repair
of the selected Tutor. The original `p8-tutor-selected-v19-development` remains
frozen in its separate checkout; its real three-turn trial failed. See the
[Phase 1-C diagnosis](../eval/phase1c-failure-repair/REPORT.md).
`lecturelens_real_eval.tutor.selection_app:create_app` remains Mock-only and was not
started. Its source-extracting default Mock does not meet the new teaching gate;
positive tests inject explicitly authored providers. Product defaults remain unchanged. Java retains authenticated
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

Complete authorized source text and every completed learner turn remain in context.
Prior source excerpts are omitted from model history while complete publications
remain in PostgreSQL/GET; explanatory text, checked calculations and Socratic
questions remain available. A teaching answer needs explanation or calculation,
not source excerpts alone. This is a structural gate, not a completeness grader.
Socratic hints additionally bind a short literal focus from the current learner
question to an existing controlled hint act. No free-form solution channel is added.
Source-unit capacity tables expose the existing anchor limits. Rejected proposals
remain complete in the checkpoint; repair input carries sizes/spans and rejection
reasons instead of repeating the entire draft. Compact JSON and mode-specific
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

The old `eval/tutor-selection-v19-v1/CONTRACT.md`, manifest and smoke entry remain
historical frozen assets. That entry rejects this changed checkout; the consumed
Phase 1-B grant cannot authorize this repair. There is no new paid execution entry
or authorization. The same historical third-turn repair still exceeds the unchanged
64,000 proxy cap (69,355 after repair versus 79,793 originally). Phase 1-C is PARTIAL
and recommends simplifying before requesting a fresh real trial. No real quality acceptance, independent human review, SQL holdout,
learning effects, release or scale authorization follows from these mechanism checks.
