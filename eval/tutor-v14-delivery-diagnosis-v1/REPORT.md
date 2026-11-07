# v14 delivery diagnosis and proposed minimal change

**Diagnosis complete; historical FAIL unchanged.** This stage makes no Tutor,
identity, prompt, length, repair, budget, scoring or product-default change.
Real model/embedding/reviewer requests **0**; new provider charges **USD0**.
The recommendation below is **not implemented**. Approval is required before
behavior implementation or any real validation; no earlier grant is reused.

Started clean at `5d228c40b04cc84886b1e73c3bad300ffe0ad28e`, branch
`codex/tutor-scale-preparation`, in the requested worktree. Historical real
execution remains `81020d1abd7c89a995bf9eba153302af7481c71b`, identity
`p8-tutor-draft-repair-v14-development`. Only three stage-specific diagnostic
scripts/tests and this report/verification summary are added. Original358
artifact hashes and34 protected runtime/frozen/report files remain unchanged.

All semantic review here is **Codex nonblind source review**, not an independent
human or statistical replication. Mechanical counts and traces are rebuilt from
retained calls, requests, proposals and original sources, rather than accepted
from the prior report. The old annotation inventory is separately checked for
span/source binding and arithmetic; its labels are not an automated oracle.

## Confirmed call path and failure classification

The original16 positions remain **10 completed,2 failed,4 skipped,0 missing**;
12 attempted,10 scorable,16 outcomes reviewed. Both failures are local
`TUTOR_FINISH_FORMAT_INVALID`, not budget exhaustion or global safety stops.
They close their own conversation under the frozen v12 protocol. The second
spreadsheet session actually starts after the first failure with empty history.

| Trace | portability1 | lineends3 |
| --- | --- | --- |
| Search / initial finish / repair wire |23 /24 /25 |30 /31 /32 |
| Initial → repaired decoded text chars |1,982→1,799 |1,818→1,633 |
| Removed by model repair |183 chars |185 chars |
| Remaining excess above1,600 |199 |33 |
| Initial / repair output usage |668 /647 tokens |730 /697 tokens |
| Initial / repair UTF-8 bytes |1,988 /1,805 |1,820 /1,635 |
| Initial / repair JSON-string chars |1,997 /1,814 |1,843 /1,658 |
| Citation occurrences / distinct IDs, unchanged by repair |9 /4 |10 /3 |
| Full citation-marker characters, unchanged |594 |660 |
| Non-citation characters, initial → repair |1,388→1,205 |1,158→973 |
| Prior published-answer history in both inputs |none |turns1/2,2,722 answer chars |
| Summary |empty |empty |
| Initial evidence count → kept repair evidence |8→4 |8→3 |
| Repair request proxy / accumulated turn proxy |17,133 /39,463 |18,880 /48,534 |

The repair requests carry the **exact original outcome/text/evaluation proposal**
as untrusted `rejected_finish`, the exact kept source objects in original ID
order, and unchanged history/summary. All needed cited sources survive. No draft,
history or evidence truncation is found. Both accumulated proxies fit64,000;
repair reservations succeed. The first failure has no history at all, so history
growth cannot be a necessary explanation shared by these failures.

The actual initial system message contains the1,200-character target and hard
1,600-character limit. The finish function description repeats them, and its
JSON schema says `text.maxLength=1600`, `evaluation.maxLength=500`. The repair
observation supplies the measured initial length, hard limit, explicit rewrite
target1,200, only-one-repair warning, and kept/removed IDs. The v14 system addition
explicitly says to count the entire draft including citation IDs. Initial/repair
system messages are4,124/4,506 characters. This is an explicit, feasible length
instruction, not a missing-unit or missing-draft defect. Prompt length/attention
or draft anchoring might affect compliance, but **no causal test establishes that**.

Every wire uses temperature0, thinking disabled and `max_tokens=1200`, with no
transport/SDK/application retry. **Output tokens are not characters.** That limit
covers the provider's completion/tool arguments and does not enforce a decoded
1,600-character answer. All four relevant completion usages are below1,200, and
complete parsed finish arguments survive. There is no observed cap-truncation
failure. Full raw response bytes/finish-reason metadata were not retained, so a
specific original finish reason must remain unknown; the replay reconstructs
the tool-call envelope from saved proposals.

Validation order is material:

1. `validate_proposal()` accepts the complete proposal without publication size
   bounds, so an overlength answer can receive its durable bounded repair.
2. `TutorRuntime.act()` extracts distinct inline IDs, checks membership in this
   turn's observed union, and authoritatively re-reads **all** cited evidence.
3. It checks distinct IDs≤4, evaluation≤500, text≤1,600 using Python `len()` on
   decoded strings. Brackets, full IDs, Markdown, spaces and newlines count.
   UTF-8 bytes, JSON escapes, display width and model tokens are different units.
4. Initial size failure creates the repair observation and prepays its request.
   The second size violation raises `TUTOR_FINISH_FORMAT_INVALID` before
   `Finish.model_validate()` and publication. Both evaluations are empty; there
   are no excess/remove IDs. Only text length fails.
5. The frozen runner classifies that known local failure, records it, and skips
   dependencies. A new independent session may continue; no failed antecedent
   is invented.

Evidence locations: `agent-service/src/lecturelens_real_eval/tutor/runtime.py`
lines255–287,390–439,496–512; `contracts.py` lines36–72;
`draft_repair_runtime.py` lines23–49; `repair_context_runtime.py` lines38–56;
`eval/tutor-v14-fresh-v1/run_fresh.py` lines68–89 and308–352. Exact actual bodies
are historical `v14-frozen16-once/wire/024,025,031,032-request.json`.

## What makes the answers too long

**Confirmed:** the model preserves a verbose flat answer and repeats long
canonical IDs at many claim boundaries. Repair shortens prose only moderately
while retaining nine/ten66-character markers. Markers occupy33.0% and40.4% of
the repaired texts. Distinct-ID≤4 constrains provenance count, **not citation
occurrences**; nine or ten occurrences are legal. The runtime has a reliable
post-generation rejection mechanism, but does not construct or guarantee a
length-fitting result. Its one repair delegates that task to the same model.

**Not established:** a tokenizer defect, protocol parser bug, lost context,
unavailable reservation, inherently impossible question, or which prompt feature
caused the model to stop compressing. These two cases do not identify all causes
of poor delivery on future tasks. The two local failures also explain all four
skips; those are additional lost deliverables, not six independent model failures.

Source-audited manual feasibility examples retain every reference point and the
same nine/ten full-ID citation occurrences. They fit **1,182 /1,246 characters**.
The first preserves all four format risks, other-format caveat, TSV/CSV, plain-
text/comma definition, portability and Excel reopening. The second preserves
all three remedies, both Git filenames/filter pattern, R/worksheets alternative
and all narrowly quantified caveats. Thus required content plus citations can
fit1,600 without increasing the bound. The second example does not meet the
soft1,200 target, which is not the publication threshold.

These examples are **human-authored feasibility, not model repairs**, and are
private diagnostic artifacts, never prompts, references or runtime answers.
They do not improve any historical numerator. Removing repeated markers alone
is not a safe fix: a later distinct claim could lose its local supporting citation.
The330/462 repeated-marker characters are a measured representation cost, not
permission to delete citations or coalesce unrelated claims.

## Excel omission and the actual metric gaps

The reopening sentence exists at original spreadsheet lines76–78. Search wire28
returns it in passage `e4c3a59d…a393bb0`; the **first** evidence item in finish
wire29 contains it verbatim. The published answer cites that same passage.
The source was found, selected, serialized and available to the model. There
is no retrieval miss, projection loss or citation misbinding for this fact.

The answer has1,285 characters, leaving315 before the hard bound. It accurately
uses the OSX statement to reject Windows exclusivity and the non-CR-parser
condition to reject a universal-failure inference. It does not state Excel's
reopening/parsing counterexample. There is room for that fact with a citation,
but the cause of its omission is **unverified content selection**, not proven
length pressure. Neither replay nor the saved output reveals a reasoning trace.

There is also a **question/reference alignment limitation**. The learner asks
for the platform statement and parser condition; it does not explicitly ask to
restate Excel reopening. The frozen reference nevertheless requires that
particular corroborating fact. The answer supplies the explicitly requested
platform/conditional reasoning. Preserve strict frozen **9/16 scheduled and
9/10 completed correctness**, and **7/12 fully supported complete expected
answers**, without retroactive threshold/reference edits. Qualify the omission
as a frozen-reference completeness failure; it does not by itself establish
failure to answer an explicitly named learner subtask. No score correction is
applied. Future evaluation design should align requested obligations and required
reference points before freezing; do not put this private reference into a prompt.

The other reported gaps are entirely unobserved positions:

| Insufficient-evidence position | Rechecked outcome |
| --- | --- |
| counter4: C range storage/byte formula/uniqueness proof | Clean refusal; complete loop episode has no such theorem |
| polynomial4: IEEE754 all-mode stability bound/proof | Clean refusal; absent from complete episode |
| portability4: Excel date-conversion/edge correction | SKIPPED after portability1; no attempted refusal |
| lineends4: RFC4180 ABNF/parser state machine | SKIPPED after lineends3; no attempted refusal |

Therefore **2/4 scheduled refusals,2/2 observed**, with **zero observed wrong
refusals**. The ten context positions likewise contain six consistent published
answers and four skips:

| Context position | Evidence for consistency or non-observation |
| --- | --- |
| counter2 | Correct prior topic; exact Curie/Darwin/Turing outputs and persistent variable |
| counter4 | Refuses unsupported implementation theorem rather than inventing an antecedent |
| polynomial2 | Corrects learner's one-based pair without contradicting actual prior pairs |
| polynomial3 | Retains x5/coefs and derives0→2→22→97 from the same solution |
| polynomial4 | Refuses unsupported numerical theorem for that loop |
| lineends2 | Preserves actual prior conditional risk; no cross-turn contradiction; reference omission is separate |
| portability2/3/4 | SKIPPED, root portability1 |
| lineends4 | SKIPPED, root lineends3 |

So **6/10 scheduled consistency,6/6 observed**, with **zero observed independent
context contradictions**. Every one of32 request histories matches only actual
completed prior turns from its own session. The low scheduled refusal/context
ratios measure delivery loss here, not two extra refusal errors or four extra
context errors. Critical index tasks remain3/3. No unsupported published exclusive
addition is found; the skipped CSV clarification and failed some-only-Windows
checklist still earn no quality credit.

The annotation arithmetic remains36/36 explicit substantive pairs,35/42 direct
requiring-claim support,42/42 with the frozen seven signaled bounded derivations.
Those ratios concern published assertions only, not missing required facts or
the16 scheduled tasks. Atomic claim granularity is Codex annotation judgment;
the compound-list convention and derivation sensitivity remain disclosed rather
than redefined to improve the gate.

## One preferred minimal proposal — not implemented

**Use short, turn-scoped display citation references with a durable canonical
mapping in a new explicit development candidate.** Preserve every claim and
local citation occurrence; remove serialization overhead rather than demand more
model self-counting. This is an **output-protocol change**, requiring review and
approval, not a patch applied in this stage.

A representation-only counterfactual replaces each full marker with an eight-
character illustrative `[cite:1]` label while keeping every surrounding character
and citation position. Exact inverse substitution restores the original text:

| Existing draft | Existing chars | Hypothetical short surface |
| --- | ---: | ---: |
| portability initial |1,982 |1,460 |
| portability repair |1,799 |1,277 |
| lineends initial |1,818 |1,238 |
| lineends repair |1,633 |1,053 |

All four would fit the **same1,600 rendered-character hard bound**, without
deleting a fact or citation. This arithmetic is not a protocol implementation,
candidate validation or real quality result. Expanding back to full IDs before
the existing length check would restore the old excess and **would not fix it**.
That is why the visible-text/canonical-metadata contract must be explicit.

Proposed implementation scope after approval:

- Add an opt-in runtime variant beside `tutor/draft_repair_runtime.py`, with a
  per-turn map in its durable checkpoint. Extend the current map deterministically
  as searches add observed evidence; never renumber within the turn or authorize
  IDs from history. Preserve the complete authoritative selected union.
- Resolve only recognized display tokens to canonical IDs before ownership,
  revision, deletion and publication checks. Keep canonical IDs/member provenance
  in citation metadata; retain the display map with the stored answer/repair so
  restart and audit resolve exactly the same source. Unknown/foreign/stale labels
  must fail closed. Validate text≤1,600/evaluation≤500 on the exact displayed text,
  with at most four distinct canonical IDs and the same bounded repair/budgets.
- Define the new variant's finish/display contract without modifying shared
  frozen `runtime.py`, `contracts.py` or `citations.py` behavior for v14. Add a new
  development identity/manifest through the existing opt-in eval mechanism; leave
  old hashes/defaults intact. The existing short-reference mapping pattern in
  `lecturelens_agent/study/context.py:219–223` is an engineering precedent, not
  authorization to change that separate product path.

Expected benefit: substantially more room for source-grounded prose at the
observed citation density, with no extra model call or weaker source requirement.
It targets the demonstrated representation cost; it does **not** guarantee the
model will preserve all required points, obey length limits or choose the right
source. It does not resolve the Excel question/reference ambiguity.

Risks: display/source rebinding, alias collisions with programming notation,
cross-turn reuse, unstable numbering after a second search/restart, consumer
rendering compatibility, and accidentally checking the short form while exposing
an overlong expanded form. The stored/presented character contract changes even
though its numeric threshold stays1,600; completion cannot be compared as a pure
model-quality effect. Retain canonical traces and disclose the protocol change.
If the consumer cannot preserve the mapping without changing production behavior,
stop and narrow the candidate interface rather than silently altering it.

Estimated scope: **2–3 engineering days** for one opt-in variant, explicit contract
and development identity, mapping/recovery/authority/display tests, and offline
regression/reporting. No CI or general evaluation-platform expansion is needed.
No increase to length, repairs, calls or money is proposed.

Zero-cost checks could prove bijection/inverse rendering, all citation anchors
retained, length computation including Unicode/Markdown, canonical authority,
second-search/restart stability, code-bracket noncollision, unknown-label rejection,
failure/skip accounting, and v14 historical replay compatibility. Fresh real
validation would still be needed for length compliance, required-point retention,
source support/coverage, absence of exclusive additions, delivery rate and cost.
This stage neither implements nor executes those future checks/trials. Lowering
output tokens is not a character guarantee, and more of the same compression
prompt is not supported as the preferred next change by this evidence.

## Offline replay and verification

Final diagnostic collection/execution: **13 collected,13 passed,0 failures,
errors or skips**. Pytest7.55s; supervisor8.538s, exit0. The full frozen entry runs
with `--mock`, an explicitly injected `httpx.MockTransport`, and a disposable
schema in the dedicated PG. The retained32 tool-response envelopes reproduce
**all32 request bodies byte-for-byte**, all10 published answers, both format
failures, all four dependency skips and independent-session continuation. PG
matches12 attempted turns/four sessions/64 ledger events. These reconstructed
envelopes are not original raw HTTP response bytes and cannot demonstrate model
intelligence or a successful repair.

Additional tests cover both exact rejected-draft/evidence views, decoded character
boundaries1,599/1,600/1,601, Chinese/emoji/newlines, all32 actual-history bindings,
Excel presence, scheduled/observed metric denominators and manual-feasibility
labelling. All new tests are collected. Final Ruff checks pass on the three
explicit diagnostic paths. No directory formatter touches any source/frozen asset.
The initial rehearsal passed12 tests; a final history-binding test brings the
suite to13. An import-order lint finding was corrected before final collection
and execution; the earlier run/log remains separate.

Actual supervised commands:

```sh
python3 scripts/dev/run_check.py --name v14-diagnosis-collect --timeout 1200 --output .data/tutor-v14-diagnosis-20261107/checks -- agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-v14-diagnosis-20261107/network-collect scripts/dev/check_v14_delivery_diagnosis.py --output .data/tutor-v14-diagnosis-20261107/collection --collect-only
python3 scripts/dev/run_check.py --name v14-diagnosis-final --timeout 1200 --output .data/tutor-v14-diagnosis-20261107/checks -- agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-v14-diagnosis-20261107/network-final scripts/dev/check_v14_delivery_diagnosis.py --output .data/tutor-v14-diagnosis-20261107/final
```

Outputs are single-use; the two stage-owned directories were created beforehand
with the source-audited private manual example file. They are not model inputs.
`safe_exec` strips provider/proxy environment and fences sockets; fixtures reject
credential access and real HTTP transports. Three Python network records show
zero external connection attempts. Native libpq is outside those Python counters;
the real PG transactions/reconciliation establish DB coverage. Original219/249
mechanism suites were not rerun for this diagnosis-only change; the unchanged
entry still verifies the frozen219 record and its artifact hashes.

Private evidence: **`.data/tutor-v14-diagnosis-20261107/`**. See
`final/diagnosis.json`, `final/replay-result.json`, JUnit/check logs,
`independent-review.json`, `manual-feasibility.json`,
`protocol-feasibility.json`, `verification.json` and `cleanup.json`.
The108-file manifest SHA-256 is
`b76388125efe3b1b012a94f6c3c645b8d04ba953f0044caecf01396a0a44e5c1`.
Replay ledgerUSD0.046152 is **simulated retained usage**, not a new charge.

Only the exact stopped dedicated PG was temporarily started. It is now stopped,
exit0, port25841 closed, evidence volume retained; no diagnostic schema remains.
Original64 real-run ledger events and all23 original running services remain
unchanged. No other workspace, production/student/manual-account data, SQL
holdout, credentials, remote publication or default identity was touched.

**NOT_RUN:** implemented fix effectiveness, real repair/quality effect, cost
optimization, independent human agreement, SQL holdout, expansion and learning
effects. Stop here; implementation and real evaluation await separate approval.
