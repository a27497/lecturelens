# Bounded Tutor usability phase — v18

**Normal teaching was overrestricted in v17.** The actual PG reproduction rejects
a supported paraphrase because the publication language permits only exact
excerpts/checked values. The new opt-in **`p8-tutor-usable-v18-development`** admits
bounded source-anchored explanations, code and specific feedback. This deliberately
reopens a model interpretation surface: **an unsupported explanation with a real
anchor can publish, so A03 is not closed**. Labels and passing mechanism tests do
not prove semantic correctness. Socratic generated text still has no free solution
channel; general body/index hint acts improve available guidance.

The new answer/feedback limits are **4096/1024 Unicode code points**, including
all full citations and labels, with **4096 output tokens** reserved separately.
The complete teaching fixture measures2721 characters /3025 UTF-8 argument bytes;
maximum schema-valid answer/feedback renders3989/950. This is a separately
versioned capacity change, not a better result under old1600/500 or a rescore of
old FAIL. [CONTRACT.md](CONTRACT.md) gives provenance, exact units, capacity basis,
actual path, resources and semantic tradeoffs. No answer is truncated.

**Technically ready for a small development smoke approval; no real request is
permitted yet.** Code, three questions, references, passing criteria and executable
entry are frozen and Mock-tested. Only a fresh exact-scope paid grant is absent;
the public-document price/config review is available and expires after24h.
Account/provider availability is NOT_RUN; the first approved request may fail
and stop the run. No independent human blind review is claimed or imposed as a
precondition for this bounded development diagnostic. Full16 is a later decision.

## Versions and bounded scope

Started clean at `eb01d290c18c6c4a63a8af1ea7a350aaf98e1dd1`, in the requested
worktree only, branch `codex/tutor-scale-preparation`.

| Local commit | Contents |
| --- | --- |
| `4db4f05cf834a8dd8db155e58565afefc88b2b4d` | Actual verified runtime/factory, limited schema/length change, tests, three-turn entry and source-reviewed packet |
| `af80398` | Frozen candidate manifest, unchanged bytes used in actual entry tests |
| Delivery commit | This report, evidence index and final review only; resolve with `git log -1 --format=%H -- eval/tutor-usability-v18-v1/REPORT.md` |

Manifest SHA-256: `34ddb43cdab734b630bc58637cd1497b418ffca1b631414c9e490049502f4950`.
Packet SHA-256: `ade24dceaf2bf50421b88373b68ebb65ba776c0d83754cab350fc06f558ba60e`.
The manifest binds22 files, source commit and parent identity; full source roots
are checked against that commit. Final Python and cross-service execution used
this source commit and the identical manifest bytes before the manifest-only
freeze commit. The final delivery changes no candidate source/material.

No default Tutor identity, historical module/asset/question/result, database schema,
public Java/browser protocol, CI or deployment changes. Java/Vue additions are
regressions only; all43 inherited explicit parent files remain unchanged. Runtime
ownership, current-turn observed evidence, authority re-read, revision/deletion,
canonical ID binding, persistent budgets, cancellation/usage, idempotency and
exclusive non-public schema requirements remain. No production/student/manual
account or credential is used; no push, PR, merge, deployment or server rental.

## Normal and adversarial evidence

All evidence below is **offline Mock/protocol behavior**, not new generation quality.
Private local root: `.data/tutor-usability-v18/`; final Python root `final-python/`.

| Case | Actual result / evidence |
| --- | --- |
| Supported non-verbatim explanation | V17 fails `TUTOR_SUPPORT_INVALID`; v18 completes with literal binding. `v17-normal-paraphrase-rejected.json`, `normal-paraphrase.json` |
| Complete explanation, conditions, code/indexing and legitimate comments |2721-character answer saved/restored unchanged with3 bound citations, tail, indentation and `names[0]`. `normal-long-teaching.json` |
| Normal calculations, CJK/emoji/newline maxima | Checked arithmetic/range/list outputs work; four900/two384 render maxima fit without changing counting. Python test results |
| Targeted Socratic guidance and history feedback | New `locate_body` question withholds numeric solution; next reply receives specific source/learner-bound feedback and exact prior context. `normal-targeted-hint.json`, `normal-hint-and-history-feedback.json` |
| Insufficient evidence / no positive match | Exact abstention and zero citations; separate positive explanation cases still complete. `normal-insufficient.json`, `normal-no-hit-insufficient.json` |
| Wrong anchor, false source excerpt, fabricated/embedded ID | No answer/citations published; bounded support correction or fatal binding rejection. `adversarial-*.json` |
| Calculation comment / spelled-out full solution in Socratic | Rejected without publication. Legitimate teaching-code comments remain allowed. `adversarial-calculation_comment.json`, `adversarial-free_solution.json` |
| Oversize / repeat oversize | Full draft retained; one correction succeeds, repeated violation fails. No slicing. `format-repair-*.json` |
| Wrong learner span / late cancellation | Bad feedback rejected; canceled turn publishes nothing while known late usage is recorded. `adversarial-wrong_learner.json`, `cancel-with-late-usage.json` |
| Unsupported free explanation with genuine source anchor | **Accepted negative fixture; unresolved semantic risk, NOT a quality pass.** `RESIDUAL-unsupported-explanation-NOT-QUALITY-PASS.json` |

A limited source-alignment pass corrected the initial normal fixture's indexing
anchor from an error paragraph to the actual first-element rule, through its real
retrieval query, and removed an explanation outside that span. Original course
lines45,135,152,193/194 and hashes are recorded in the new reference review.
The same Codex author wrote/reviewed the packet, implementation and tests; no
independent human or independent AI cross-review is claimed. This is exposed
known-course development material, not held-out selection or formal gold.

Two retained v14 failures are reconstructed from parsed proposals only:
1982→1799 and1818→1633 characters, with594/660 citation-marker characters. They
fit4096 by **size only**; no new-protocol conversion, generation success or old
score improvement is inferred. Original bytes of those responses are unavailable.
All historical FAIL remain FAIL. `length-measurement.json` identifies wire sequence,
proposal hashes, counts and reconstruction status.

## Actual entry and checks

Entry: **`scripts/dev/run_tutor_smoke_v18.py`**, default verify-only.
Product factory: **`lecturelens_real_eval.tutor.usable_app:create_app`**, Mock-only.
Detailed exact supervised command arrays, exits, times and artifacts are in
[VERIFICATION.json](VERIFICATION.json). Long commands use `scripts/dev/run_check.py`;
PG is a new bounded local container from an already present pinned image, with
separate per-test schemas. No dependency/model download or real transport occurs.

```sh
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-usability-v18/network-final-python scripts/dev/check_tutor_usable.py --output .data/tutor-usability-v18/final-python
mvn -o -f backend/pom.xml -Dtutor.phase.root=/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens -Dtutor.phase.label=final-cross-service -Dtest=TutorUsableCrossServiceIT test
mvn -o -f backend/pom.xml -Dtutor.phase.root=/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens -Dtutor.phase.label=cross-service -Dtest=TutorCompleteEvidenceTest,TutorTransportTest,TutorControllerTest,StudyAuthorityTest,TutorUsableCrossServiceIT test
/opt/node/bin/node frontend/node_modules/vitest/vitest.mjs run src/components/task-detail/CourseTutorPanel.test.ts src/components/task-detail/CourseTutorPanel.usable.test.ts --root frontend --config vitest.config.ts --reporter=json --outputFile=/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens/.data/tutor-usability-v18/vue-results.json
/opt/node/bin/node frontend/node_modules/vue-tsc/bin/vue-tsc.js -b frontend/tsconfig.json
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-usability-v18/network-v17-compat scripts/dev/check_tutor_guarded.py --stage 'source_publication or guarded_value_language or hint or positive or default_mock' --output .data/tutor-usability-v18/v17-compatibility
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-usability-v18/network-measure scripts/dev/measure_tutor_usable.py
```

These are recorded commands, not instructions to reuse existing evidence folders.

| Check | Result / practical scope |
| --- | --- |
| Final Python/PG + actual frozen entry |38 passed,0 skipped; semantic negative cases are explicit negative evidence |
| Java targeted mechanisms |24 passed,0 skipped; full signed Java→ASGI/PG→Java authority |
| Cross-service at final source commit |1 passed again,0 skipped; two sessions, replay/cancel, owner/revision checks |
| Tutor Vue regressions and new long display |18 passed; escaped HTML, full answer/feedback, citation action and no send on restore |
| Vue type check |exit0 |
| Old v17 affected compatibility |10 passed,59 deselected intentionally; old bytes/identity unchanged |
| New Python lint/format |10 explicitly named files,0 diagnostics / format pass; no old formatting |
| Python compile |10 files pass; not a static type check. No configured/installed Python type checker was run |
| Actual default CLI |exit0; no dispatch/DB/key lookup |
| Actual unapproved live CLI |expected exit2 `V18_LIVE_RECEIPTS_REQUIRED`; no output directory/DB/transport/key lookup |

Actual frozen Mock entry results (3 scheduled positions per fixture):

| Fixture | Complete / fail / skip | Sends | Stop |
| --- | --- | ---: | --- |
| Normal |3/0/0|6|None; quality NOT_RUN|
| One format correction per non-Socratic turn |3/0/0|8|None; full drafts retained|
| Repeated format violation |0/1/2|3|TUTOR_FINISH_FORMAT_INVALID|
| Invalid support |0/1/2|3|TUTOR_SUPPORT_INVALID|
| Fabricated ID |0/1/2|2|Wrapped protocol failure; durable fabricated-ID root retained|
| Malformed response / unknown usage |0/1/2 each|1 each|Whole smoke; full unknown liability retained|
| Returned model mismatch |0/1/2|1|Whole smoke|
| Request budget fault |0/1/2|1|Before second send|

These26 sends are simulated fixtures, not26 paid samples or tutoring successes.
Actual request bodies use deepseek-flash/4096/temperature0/thinking-disabled and
contain no reference/scoring fields. Raw Mock request/response entity bodies and
capture/redaction status are retained before JSON parsing. The12th ledger
reservation succeeds;13th fails before a send. Fee accounting remains conservative
and append-only. Initial test-authoring failures (JSON-escaping comparison and
incomplete route fixture) are retained; neither changed product limits. Final
review also examines raw evidence and code in [FINAL_REVIEW.md](FINAL_REVIEW.md).

## Approval proposal, remaining limits and stop

[SMOKE_PLAN.md](SMOKE_PLAN.md) proposes exactly **3 development turns**, exact API
ID **`deepseek-flash`**, at most3 ordinary decisions plus1 format correction per
turn, **12 requests total**, **4096 output tokens/request**, and **US$0.30 reserved
plus settled liability**. Worst full-wire reservations total US$0.294912 at the
frozen no-cache peak rates. No reviewer/embedding requests, auto-tuning/retries,
reruns, default activation or automatic full16 follow. Engineering/provider/protocol/
usage/authority/budget/correction failure stops the entire smoke. Subsequent
source-based content judgment must pass every necessary point in all3 positions;
unsupported content or any other quality FAIL prevents a full16 recommendation.
The driver is not an automatic semantic grader. A small smoke pass still does not
authorize full16 or a release.

[PUBLIC_PRICING_REVIEW.json](PUBLIC_PRICING_REVIEW.json) records the current
[official rates](https://api-docs.deepseek.com/quick_start/pricing/) and
[documented configuration](https://api-docs.deepseek.com/api/create-chat-completion/)
check at2026-11-07T18:23:48Z, with no account/API/credential access. Its price/config
receipt is valid only within the admission's24h window; a fresh grant is still
required. The default verify output lists required receipt categories, not a claim
that documentary review requires another implementation/preparation phase.

Remaining risks: unsupported explanations, source crops/false source claims,
code/derivation relevance, feedback correctness and hint targeting require semantic
judgment; source inspection can reveal solutions. Tokenization/output compliance,
20s latency and budget feasibility with real history remain NOT_RUN. The new
ceiling does not guarantee every maximal Unicode/anchor combination is generatable.
No migration or large refactor is needed for this opt-in phase; mixed-worker
activation would still require separate scope. Full16 and arbitrary unseen
source/question combinations were intentionally not checked.

**New real model/embedding/reviewer calls0/0/0; fee US$0. Real quality improvement,
cost optimization, independent human agreement, SQL holdout, scaling and learning
effects remain NOT_RUN.** The owned temporary PG container was removed only after
all owned schemas/public tables were empty. Port25841 is closed, evidence retained,
and all23 original running containers remain. No original service was stopped.
This phase ends here and awaits approval; no paid or publishing phase follows.
