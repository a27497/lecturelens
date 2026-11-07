# v12 failure audit and minimal v13 intervention

The v12 original-sixteen run completed all positions, but did not meet its frozen
quality gate. The starting repository was clean at
`837915cc49837b0f2e5fb003ab21adc5f7c53567`. Its actual execution code was
`8358595c792b5ce28f965a5c724a0dc6d8b076bd`. Historic raw evidence and scores remain
unchanged. This audit uses exact recorded requests, parsed proposals, source
Markdown, context history, canonical citations and the original claim inventory.
It is Codex nonblind review, not independent human assessment.

## Three nonpassing whole answers

1. **`fresh-python-tail:1`, incorrect:** the question window 502–515 reached the
   model; output 519–522 did not. The passage builder splits at every heading,
   including `Solution`. The output-only window lacks the query's words, so it
   is not in that search's top eight. The model then said the whole unit did not
   print the negative-index values, although the original source explicitly
   prints them. This establishes a structural retrieval-window limitation and
   an unjustified whole-unit absence assertion. It does not reveal hidden model
   reasoning or prove that more context alone will fix generation.
2. **`fresh-python-functions:1`, uncertain:** both mean/input and no-explicit-input
   invocation/time passages are in the final request. All required points are
   present. The additional “not an argument list” contrast is not established by
   the unit and can deny empty-argument-list syntax. The per-machine-clock
   application is also uncited. No retrieval or parser defect is demonstrated.
   The original uncertain judgment remains; this audit does not rewrite the
   answer into the narrower reference.
3. **`fresh-sheets-markers:3`, uncertain:** the metadata and NA table passages are
   observed, and actual earlier clarification is present. The answer refers to
   an unspecified “null marker” instead of making the consistent missing encoding
   explicit after NA means North America. The retained rejected draft already
   has that generic wording; there is no evidence the repair removed a concrete
   encoding. This is a completeness/specification concern, with semantic
   uncertainty retained, not a proven context or repair-loss defect.

## All fifteen original coverage gaps

Every row is linked to its exact final request, source excerpts and original claim
span in private `cause-audit.json`. “Available” means the relevant lesson premise
was observed, not that an internal model attention process was measured. Source
existence and claim-level entailment are different properties.

| Original claim | Output / context finding | Classification |
| --- | --- | --- |
| tail:1 c1, last character | Correct result, no local citation; direct printed output not retrieved | Retrieval limitation plus citation omission |
| tail:1 c2, second-last character | Correct result, no local citation; direct output not retrieved | Retrieval limitation plus citation omission |
| tail:1 c5, endpoint explanation | Correct derivation; endpoint/suffix premises available; no attached citation | Citation omission |
| tail:3 c3, boundary explanation | Short-input solution available; separate explanation uncited | Citation omission |
| tail:3 c4, upper exclusion | Locally cited 264–294 explains omitted bounds, not the exclusion claim; rule exists elsewhere | Local attribution mismatch |
| tail:3 c6, short-string explanation | Required short-input output available; explanatory sentence uncited | Citation omission |
| sheets-text:1 c6, strip/replace advice | Character restriction observed; added application uncited; no actual repair claim | Citation omission |
| sheets-text:2 c1, specific newline warning | Full unit says it, but attached summary only says avoid special characters | Local attribution mismatch |
| sheets-text:2 c5, row-specific note | Separate-field premise observed; application uncited | Citation omission |
| sheets-text:2 c8, one-piece-per-cell | Summary observed; added instruction uncited, unlike already inventoried destination restatements | Citation omission |
| functions:1 c5, syntax contrast | Invocation premise observed; added contrast not established | Unsupported addition, no retrieval explanation |
| functions:1 c7, current machine clock | Source current-time example observed; added application uncited | Citation omission; exact clock-source behavior not established |
| markers:1 c7, tolerated spelling policy | Relative recognition table observed; policy suggestion separately uncited | Citation omission, not universal-parser proof |
| markers:2 c3, document region meaning | Metadata and clarified region available; documentation bullet uncited | Citation omission |
| markers:5 c5, repeated type risk | Paraphrases the already inventoried, cited uncommon/type-risk claim c4 | **Scoring duplicate** |

The publication code validates observed/authoritative IDs and bounded protocol,
not per-claim semantic entailment or citation placement. That is a proven contract
limit; it is not evidence of a broken canonical ID map. Specific causes such as
model attention, preference for an uncited summary or repair-induced semantic
loss are **unverified** unless explicitly established above.

### Additive scoring correction

Under the unchanged distinct-claim definition, markers:5 c5 adds no fact beyond
its cited c4. The original inventory should deduplicate that paraphrase. Original
reports/raw scores are preserved. Supplementary corrected v12 figures:

| Metric | Original reported | Audited correction |
| --- | --- | --- |
| Complete correct | 13/16, one incorrect / two uncertain | Unchanged |
| Supported explicit pairs | 59/62 | Unchanged |
| Citation presence | 61/74 | **61/73** |
| Supported requiring assertions | 59/74 | **59/73** |
| Full expected-answer coverage | 3/12 | **4/12**, adding markers:5 |
| Frozen decision | FAIL | **FAIL** |

This corrects duplicate counting, not a question, reference or threshold. Other
uncited explanations can introduce distinct premises; they are not automatically
removed merely because the final result was previously cited. The new rubric
states semantic restatement deduplication before any new candidate result.

## Minimal v13 changes and limits

`claim_grounding_runtime.py` subclasses the frozen v12 runtime. A source-only
projection joins a short question window with its immediately following
`Solution` window when their combined text is at most the existing 1,000-character
grouping bound. It preserves exact source/member IDs, text and locators, hashes a
new context identity, and never crosses a source/out-of-order boundary or an
ordinary section heading. Oversized indivisible original blocks retain existing
fail-closed runtime protection. No reference or evaluation label enters retrieval.

One general system instruction requires checking all requested parts/corrections,
distinguishing retrieved coverage from full-unit coverage, and attaching supporting
observed citations to factual results, explanations, applications and optional
recommendations. It forbids using examples as universal rules or unverified
quotations. It does not tell the model an answer or instruct it to remove required
content/optional assertions to inflate coverage. The same wire/context bytes,
including this instruction on prepaid repairs, are reserved under existing limits.

The candidate has a new manifest, explicit development entry and source-context
identity. v12 and all earlier candidates remain reproducible; defaults are not
registered or switched. Tools, turn/session/call/money limits, four-citation and
1,600/500-character publication limits, one format/one mode repair, and the v12
local/global failure protocol are unchanged. There is no extra reviewer, semantic
repair loop, automatic citation filler or semantic success relabeling.

The source-window fix is deterministically verified on the actual missed query.
Prompt effects on completeness, unsupported assertions and citations are
**hypotheses until the new real trial**. An explicit negative Mock fixture retains
unsupported answers with valid IDs as mechanically completed but semantically bad;
no unit test is used to claim the model now understands sources.
