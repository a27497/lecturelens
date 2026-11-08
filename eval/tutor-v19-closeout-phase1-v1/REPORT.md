# V19 closeout phase1: isolated recovery and teaching protocol acceptance

**Isolation and frozen-file verification PASS. Normal teaching is permitted by
the actual model-output protocol and survives the controller/storage/UI path.**
No product regression requiring a behavior change was found in the bounded cases;
v19 and all old/default identities remain unchanged. Real model teaching ability
is still NOT_RUN. The small smoke is mechanically prepared, pending fresh paid
approval. A03 semantic support remains a known risk, not a closed defect.

Actual model/embedding/reviewer calls: **0**. Actual cost: **US$0**.

## Recovery and versions

- New checkout: `/home/dev/.codex/worktrees/tutor-v19-closeout-20261108`.
- Created detached from **`d1eb5053b5c40fc4ed879d516845880031353ab8`**. Initial
  index/worktree clean; the new administrative record's `gitdir` points back to
  this checkout and `commondir` resolves to the existing common repository.
- Creation used `git -c core.hooksPath=/dev/null --git-dir=/home/dev/projects/lecturelens/.git worktree add --detach --lock --reason 'Authorized v19 zero-cost closeout; preserve both checkouts' /home/dev/.codex/worktrees/tutor-v19-closeout-20261108 d1eb5053b5c40fc4ed879d516845880031353ab8`.
  No existing directory was reused. No init/reset/clean/prune/repair, branch move,
  shared configuration change or old `.git` rewrite occurred. Hooks were disabled
  for this command only; no configuration was persisted.
- Actual execution HEAD for the checks: `d1eb5053b5c40fc4ed879d516845880031353ab8`;
  the new authored HTTP test was present and is now committed byte-identically as
  **`50e3d408472f0a0a013cc159830c3f79f7961f9c`**. Later delivery changes are documents
  and evidence only. Resolve the final delivery SHA via the commit containing this
  report; the user-facing delivery records its full SHA.
- Runtime identity remains **`p8-tutor-selected-v19-development`**; code commit
  **`ae222cc76ec41aed78072713a9371eaff6000b2e`**. Existing candidate hash
  **`16a094317ba06b3c1932280c7dbb15a07d47200dc74ed8e08e25465e10549ae9`** and packet
  hash **`ade24dceaf2bf50421b88373b68ebb65ba776c0d83754cab350fc06f558ba60e`** remain.
- All18 v19 and22 parent-manifest entries match their original hashes, including
  all three previously missing scripts. The manifests were not changed to fit.

The original branch still points to `d1eb505...`; the old pointer hash is unchanged.
Both checkouts are retained. All new changes and test outputs reside in the new one.

## Old-directory comparison

`OLD_DIRECTORY_DIFF.json` lists every detected difference from the original commit:
2244 tracked paths;73 missing; no content or mode changes among inspected paths.
Nine conservatively protected paths were not read, including `.env` examples and
credential-named paths. They are not asserted unchanged. One extra file is
`.demo/lecturelens-sample.mp4`; its content was not read. Thirty-one cache/build/
private directories are listed as opaque extras and were not traversed. No unknown
file or dependency installation from the old checkout was copied.

The missing files include the73 listed scripts (including the three v19 scripts);
the complete new checkout contains their committed versions. **Old staging state
is UNKNOWN:** its original per-worktree index is absent. Detaching from the full
commit does not recover that index or relabel old deletions as intentional repairs.

## Actual teaching protocol and publication path

`selection_runtime.py:Source` has only `kind` and `span`. This branch is for raw
excerpts. **`Explanation` separately has generated `text` (900 code points) and a
supporting span; `Feedback` has generated `text` (384), a current learner quote and
span.** Code and conditional derivation are ordinary explanation text; they need
not be copied from the course. `SYSTEM` explicitly permits paraphrase, teaching
code and conditional reasoning. The supplied JSON Schema advertises these fields
to the actual provider, not merely to a helper test.

In `SelectedTutorRuntime.act`, the selected interval produces the support quotation;
the explanation/feedback text is retained. `UsableTutorRuntime.act` validates
bindings, mode, learner quote and limits, rechecks source authority and atomically
stores the rendered answer/evaluation. It does not require explanation text to be
a source substring. Labels distinguish Source from Explanation and describe feedback
as model interpretation. The frontend displays completed stored text with escaped
HTML and preserved whitespace; full original citations are separately inspectable.
It does not display unvalidated streaming model text or truncate code/index brackets.

The default `SelectedMock` chooses source excerpts for deterministic mechanics.
That is **not a restriction on the real `tool_calls[].function.arguments` protocol**.
The explicit smoke uses the same actual channel/provider/runtime with a live
transport only after admission. Authored response bodies entered at the HTTP
transport in this phase; no controller, schema, authority, admission or ledger was
stubbed. This proves protocol/delivery capacity, not that a real model will generate
the required answer.

**Exact source attribution is not semantic correctness.** The retained A03 negative
case accepts a true loop source with “Every loop cures influenza.” No semantic
guarantee is inferred. Invalid unit bounds are rejected/corrected; a valid but
irrelevant interval still requires semantic review. Socratic uses finite hint acts;
the indentation question is available, but arbitrary pedagogical relevance is not
proved. No refusal blanket, extract-only workaround, keyword stack or new identity
was introduced.

## Bounded cases and results

Private root: `.data/tutor-closeout-phase1-v1/`. `protocol-proof.json` contains the
actual wire schema, measured rendered lengths, source catalog/history sizes,
request sizes, request counts and durable per-turn reservations for five new cases.

| Case | Observed outcome |
|---|---|
| Complete authored explanation/conditions/changed trace/commented Python/indexing | Four explanation blocks,2721 code points; no extract-only substitution. Fixed trusted authored code produces4 in an isolated Python process. |
| Three connected teaching turns | First and third answers2721; targeted Socratic question246; specific feedback349 code points. Prior answers persist unchanged into later requests.7 Mock requests. |
| Two searches, format error, one valid finish correction |4 requests on first turn,60217 reservation proxy; full answer saved; whole packet8 requests. |
| Two searches, bad interval, one valid correction |4 first-turn requests,59681 proxy; same full answer saved; whole packet8 requests. |
| Format→interval error or interval→format error | Exactly4 sends, one shared repair journal;0 completed/1 failed/2 skipped. No fifth request or answer publication. |
| Evidence miss, source mutation, cancellation, restart, foreign IDs, embedded citations, invalid intervals, expression-comment and free Socratic answer carriers | Existing bounded regressions pass; no invalid publication in those cases. |
| Real anchor with wrong explanation | Known negative remains accepted; explicitly a residual semantic defect, not a quality pass. |

Body4096/evaluation1024 limits remain complete Python Unicode code-point counts,
including headers, separators, labels and full citation IDs. They are not output
token counts. Output4096 tokens, wire65536/131072 bytes,20s deadline,64000 turn/
640000 session proxy and local ledger guards remain unchanged. No truncation or
relaxed criterion was used. The actual fourth request advertises finish only;
format and span errors cannot each obtain a separate correction.

## Verification and evidence gaps

All long commands used `scripts/dev/run_check.py`; exact argument arrays, logs,
exit codes and timing are in `VERIFICATION.json` and private `checks/`.

```text
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-closeout-phase1-v1/network-v19-final scripts/dev/check_tutor_selected.py --stage 'not historical and not replays_original_response_bodies' --output .data/tutor-closeout-phase1-v1/v19-final
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-closeout-phase1-v1/network-teaching .data/tutor-closeout-phase1-v1/check_teaching.py
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-closeout-phase1-v1/network-v18-compat scripts/dev/check_tutor_usable.py --stage 'not frozen and not invalid_grant' --output .data/tutor-closeout-phase1-v1/v18-compat
mvn -o -s .data/tutor-closeout-phase1-v1/maven-settings.xml -f backend/pom.xml -Dtutor.phase.root=/home/dev/.codex/worktrees/tutor-v19-closeout-20261108 -Dtutor.phase.label=closeout-cross-service -Dtest=TutorSelectedCrossServiceIT,TutorCompleteEvidenceTest,TutorControllerTest,TutorTransportTest,StudyAuthorityTest test
npm --prefix frontend run test:unit -- src/components/task-detail/CourseTutorPanel.test.ts src/components/task-detail/CourseTutorPanel.usable.test.ts
npm --prefix frontend run type-check
```

- V19: **39 passed,0 skipped**, two historical-response cases deliberately not run.
- New actual HTTP teaching/shared-correction cases: **5 passed,0 skipped**.
- Old identity compatibility: **27 passed,0 skipped**;11 old frozen-entry/grant
  cases deliberately outside this compatibility selection.
- Java/actual cross-service Mock: **24 passed,0 skipped**; authenticated gateway,
  real Evidence authority reads, HTTP/ASGI and isolated PG; synthetic identity,
  retrieval/model, replay, two sessions, owner404 and revision409.
- Vue: **18 passed**; `vue-tsc -b` exit0. Named Python Ruff and compilation exit0;
  Python compilation is not described as static type checking.

Python and Node dependencies were installed from lockfiles/local caches offline
into the new checkout; Maven ran offline with an empty explicit settings file.
The first Node bootstrap double-loaded `/dev/null` as two configuration roles;
distinct empty files fixed setup. The first test-name selection accidentally
included one unavailable raw-response test:39 passed/1 missing-artifact failure/
1 deselected. That failure remains recorded. Correct explicit selection yields
39 passed/2 deselected; no historical FAIL or test implementation was rewritten.

The v18 original response bodies are currently unavailable. **Both original-body
replays are NOT_RUN in this phase**, not reconstructed or fabricated. Earlier replay
reports remain historical evidence, not new execution. All new HTTP responses are
hand-authored Mock fixtures; no new genuine generation was observed. The unavailable
history affects that replay only; the original candidate and new complete teaching
protocol are independently traceable through committed files and fresh Mock captures.

## Reference review, smoke decision and cleanup

The same three exposed development questions, references and source hashes remain
frozen. Per-item source support/ambiguity is in the unchanged reference-review pack:
loop per item (source135), increment/unindented final print (193–194), indexing45,
body boundary152. Start2 with Ada/Grace is an explicit learner assumption yielding
2→3→4, not a replacement of the original course output. Source and references align
for these bounded questions; all original required points remain. Reference/scoring
fields are absent from actual product requests. Review is disclosed same-author
Codex AI self-review, not independent human review/agreement.

`SMOKE_APPROVAL.md` is the sole proposed continuation; `EXECUTION_BINDING.json`
identifies the unchanged candidate and actual code. Official public documentation
was rechecked on2026-11-08 at14:49 Shanghai time; peak input/output rates remain
US$0.30/US$1.20 per million, matching the conservative local policy. Public docs do
not establish account access, an immutable backend or supplier actual billing.
No grant has been created and no live request was made.

Only the exact labelled disposable PG container created here was removed after all
schemas were dropped and other DB connections reached0. Port25841 is closed; all159
original containers remain present. Both checkouts, environments and evidence remain;
no original service was stopped. No push, PR, deployment, CI or default change.

**NOT_RUN:** real quality improvement, cost optimization, independent human
agreement, SQL holdout, full16/expansion, learning effects, original-body historical
replay, account availability and supplier billing. General entailment/completeness,
unseen-course behavior, multi-worker stress and real browser interaction are outside
this bounded check. Python audit counters exclude native libpq and Java/Node and
are not an OS-wide egress proof. Work stops before paid execution.
