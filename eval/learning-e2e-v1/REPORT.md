# Mock learning-flow acceptance — 2026-11-07

**PASS for the bounded desktop Mock functional scope below.** No confirmed
product blocker was found; no product runtime, default identity or scoring rule
was changed. The fixes in this task concern the new acceptance script's desktop
locator, fault injection and DOM-text comparison. They do not establish improved
model quality. This is Codex functional/source review, not independent human
teaching-quality assessment or a release decision.

## Version and environment

- Worktree: `/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens`;
  branch: `codex/tutor-scale-preparation`. Starting clean HEAD:
  `829a70ff46211fc2614be7f8fb8c9d0aabd39f3b`.
- Final successful browser execution: clean commit
  **`990662f6158f7ecdfeda447c16d252117f51f488`**. The following report/summary commit
  changes documentation and evidence metadata only; no subsequent executable
  change requires a new stack run.
- Vue/Java were built and tested from starting HEAD. Python mechanism tests
  recorded `d3bc7ca392871d133206e839ba023871625a2117`. All `frontend/`, `backend/`
  and `agent-service/` files are identical across these versions and the successful
  browser commit. Task changes are confined to `eval/learning-e2e-v1/`.
- Comparison uses the locally recorded `origin/main`
  `300be51515867f7ece4f3a9224a484e825219ee0`; local `main` is older (`fd8ece8`).
  Remote freshness and deployed version were NOT_RUN. Vue, Java and
  `lecturelens_agent` match that `origin/main`. Branch additions include separate
  Tutor evaluation adapters, tests, datasets and reports; their presence does not
  establish deployment.
- Study source identity: `p10-choice-review-442bb2af75c77ed1`, manifest
  `442bb2af75c77ed1f1a0d4b858dce9b43751b5eb4e9d9e7ff5835a5609c870ab`
  (63 modules verified). Product Tutor: original
  `p8-tutor-20261027-v9` / `TutorRuntime` + `MockTutor`; all 18 frozen file hashes
  match. Evaluation v10/v11 identities were not installed. Historical identity
  reconstruction checks passed in the Python suite; frozen inputs were unchanged.
- Actual chain: sandboxed Chrome 153 → built Vue → packaged Java 21 → actual
  Python app → newly owned MySQL/PostgreSQL, with Redis/MinIO/RocketMQ from the
  existing smoke infrastructure. One fresh `example.invalid` account, generated
  two-second synthetic video and Mock transcript; no manual-acceptance accounts.
  Offline hash embedding only; no embedding model or provider was called.
- Preview-only `AGENT_LLM_MODE=mock`, `STUDY_FEEDBACK_ENABLED=true` exercise the
  existing optional feedback path. Feedback's product default remains off.
  Empty model-connection table, five Mock-only Study Runs, active Python socket
  guard, no attempted non-loopback Agent connections; Java provider switches off.
  Browser external requests are blocked. This is not OS packet attribution for Java.
- Preflight refused existing resources under both reserved Compose project names,
  selected free loopback ports and generated secrets in memory. No application
  credential files were passed to the stack. Logs were redacted by the existing
  harness. Available memory was over 13 GiB and disk space about 44 GiB before
  execution; only bounded functional checks were run.

## Functional acceptance table

All PASS rows use code `990662f`; screenshot paths are relative to
`/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens/.data/learning-e2e-20261107/browser-05/`.
Entrances are independent product panels; navigation checks do not imply Tutor,
flashcards and practice form one adaptive learning pipeline.

| Code | Scenario / entrance | Expected behavior | Actual result | Evidence | Uncovered scope |
| --- | --- | --- | --- | --- | --- |
| `990662f` | My courses → Enter learning → Explain/practice | Ready course opens; explicit goal and format create saved exercises | PASS; choice and open practice generated through real services | `screenshots/01-generated-private-key-hidden.png`, `browser-results.json` checks 01/03a | Upload UI itself: course prepared through real upload/task APIs |
| `990662f` | Persistent course reader / video | Read synthetic original and decode actual video | PASS; 640×360 video, 13 decoded frames, playhead 0.355548 s, then pause | `screenshots/07-course-reader-and-video.png`, `mediaProof` | Long recordings, ASR quality and detailed material-tab behavior |
| `990662f` | Choice, Tutor, flashcard and feedback source actions | Open current course quotation and highlighted source; return to learning panel | PASS for all four entrances | `screenshots/03-evidence-location.png`, `08-tutor-evidence.png`, `10-flashcard-evidence.png`, `11-feedback-source.png` | Only one synthetic cue starting at 0 ms; nonzero/long-video seeking not established |
| `990662f` | Choice grading | No blank judgment or pre-submit answer-key leak; wrong/correct save immutable versions | PASS; blank direct request HTTP 400 and no stored attempt; wrong v1 and correct v2 retained | `screenshots/02-blank-still-ungraded.png`, `04-correct-restored-and-history.png` | Real generated item/answer quality |
| `990662f` | Wrong-answer review | Wrong item survives another Session and refresh; original question opens; latest correct version removes item | PASS; latest submitted totals move from wrong 1 to correct 1, wrong 0 | `screenshots/03b-review-from-another-session.png`, `03d-original-question-restored.png`, `04-correct-removes-review-item.png` | Mastery inference and adaptive remediation are not claimed |
| `990662f` | Open-answer continuation | Save text separately from optional feedback; restore saved work | PASS; open answer has no choice grade; feedback stays tied to saved answer v1 | `screenshots/05-open-text-feedback-and-completion.png`, `11-feedback-correction-restored.png` | Semantic feedback accuracy |
| `990662f` | Tutor conversation | Follow-up in same Session; Socratic prompt and reply evaluation; restore after refresh | PASS; first conversation has 3 completed turns, including Socratic prompt and subsequent evaluation | `screenshots/08-tutor-history-restored.png`, `09-both-conversations-restored.png` | Model intelligence, long conversations and answer quality |
| `990662f` | Tutor lost submission response | Explain unknown outcome; preserve text and exact retry identity; no duplicate turn | PASS; server commits, response is discarded; identical retry gives one saved turn; both conversations reopen | `screenshots/09-tutor-unknown-outcome.png`, `browser-results.json`, `synthetic-state.json` | Other browser/network failure classes |
| `990662f` | Flashcards / self-review | Flip, inspect source, rate Good, persist due queue and schedule | PASS; first deck's empty due queue survives refresh; second deck tested independently | `screenshots/10-flashcard-empty-due-queue-restored.png`, `10-flashcard-progress-restored.png` | Actual delayed return at due time and long-term retention |
| `990662f` | Flashcard lost review response | Retry original review without duplicate scheduling | PASS; two reviewed cards total, one log per card, each version 1 after retry; due queue 0 persists | `screenshots/10-flashcard-unknown-outcome.png`, `synthetic-state.json` | Independent cross-tab conflict not exercised in this browser run |
| `990662f` | Evidence feedback correction | Keep original feedback/answer; version learner check note and restore dispute | PASS; acknowledged v1 and disputed v2 both retained; source return and refresh keep answer v1 and latest note | `screenshots/11-feedback-source.png`, `11-feedback-correction-restored.png` | This marks feedback for checking; it does not correct model truth or change a grade |
| `990662f` | Refresh / panel / Session recovery | Preserve saved choice, open answer, feedback, Tutor histories and review state | PASS across 1440×900 and 1280×800 desktop viewports | Checks 03a–11; 26 screenshots, browser and PG records | Unsaved drafts across reload, exact media playhead and full browser process-restart recovery |
| — | Other verification surfaces | Separate actual UI coverage from other checks | NOT_RUN in browser: mobile/Safari, server failed/cancelled Run presentation, deletion/version-change and cross-account UI | Related unit/PG regressions below; no substitute UI PASS asserted | These are explicit coverage limits, not newly discovered blockers |

No unresolved FAIL or environment BLOCKED remains in the accepted bounded scope.
Earlier unsuccessful harness trials remain FAIL/stopped, as recorded below.

## Actual checks and independent reconciliation

Evidence root: `.data/learning-e2e-20261107/` (ignored, local only).

| Check | Result | Retained evidence |
| --- | --- | --- |
| Offline npm dependency install; frontend unit tests and build/type-check | PASS, 336 tests / 47 files | `checks/frontend-baseline/{run.json,output.log}` |
| Java StudyChoiceGateway, StudyController, StudyAuthority, TutorController, TutorTransport tests and package | PASS, 32 tests; no failures, errors or skips | `checks/java-baseline/{run.json,output.log}` |
| Separate new PostgreSQL/pgvector test instance; ten relevant Python files | PASS, 398 tests, no skips; one existing AnyIO deprecation warning | `checks/python-learning/`, `python/{targeted.log,database.json}` |
| Actual full-stack browser | PASS, 12 checks, 26 screenshots, no page errors, external requests or unread response bodies | `browser-05/{browser-results.json,stack/result.json,screenshots/}` |
| Isolated one-shot transport-fault microcheck | PASS; real local HTTP commit, discarded response and subsequent received retry | `transport-fault-check.json` |
| Independent retained-record audit | PASS; content comparisons and cleanup checks below | `independent-audit-final.json`, `independent_audit.py` |

Python files: `test_tutor.py`, `test_tutor_citations.py`, `test_flashcards.py`,
`test_scheduling.py`, `test_study_choices.py`, `test_choice_review.py`,
`test_study_attempts.py`, `test_study_feedback.py`, `test_study_resilience.py`,
`test_acceptance_cost.py`. These exercise persistent mechanisms, replay, recovery,
failure/cancellation and identity compatibility; they do not make browser-only
NOT_RUN items into UI passes. No product code change warranted broader testing.

The independent audit reads the original HTTP/PG exports without starting services:

- 4 Study Sessions, 5 successful Mock Runs, **330 events**, 2 practice artifacts,
  3 attempts (wrong choice v1, correct choice v2, ungraded open v1), 1 feedback,
  2 check notes; 2 decks/cards and 2 review logs; 2 Tutor Sessions / 4 completed turns.
- Five Tutor turn POSTs represent four unique client turns plus one exact replay;
  session-creation POSTs are counted separately (two). Two deliberate lost responses
  and the single expected blank-selection HTTP 400 are retained, not hidden failures.
  No unexpected HTTP error in observed Study POST responses or failed/missing
  required functional outcome remains. This is not an exhaustive HTTP traffic audit.
- **Content**, not just counts: all four Tutor turns are compared between latest
  HTTP views and PG for IDs, inputs, status/outcome, answer, evaluation, citations,
  usage, execution counters and error code; scope identity is compared too.
  All 3 saved attempts, 2 feedback notes and 2 review logs are compared by identity
  and their substantive fields. Exact field lists are in the audit JSON.
  Timestamp presentation is excluded. This is not a claim of exhaustive byte-level
  equality for every database table or HTTP response.
- Per-Run event sequences are unique and contiguous; this verifies sequence
  integrity, not independent semantic equivalence of all event payloads.
  Review logs and card versions prove each Good applied once. The wrong choice
  and prior feedback note remain immutable historical rows.
- Two logical PG test databases were used in a new disposable test instance;
  `python/database.json` confirms its removal. Preview exports are saved before
  teardown. Both owned Compose projects, their temporary volumes/networks and all
  selected service listeners are gone. Supervisors report complete descendant
  cleanup. All 23 existing running container IDs recorded before the final run
  remain running at the final check; none were stopped by this task.

Recompute the retained audit with a fresh output name (no API calls):

```bash
agent-service/.venv/bin/python .data/learning-e2e-20261107/independent_audit.py \
  .data/learning-e2e-20261107/audit-NEW.json
```

Cleanup/port assertions describe the current local environment and can legitimately
fail later if a different service reuses a port. Data/content assertions remain
replayable from retained artifacts. `SUMMARY.json` records non-sensitive metadata
and hashes of the principal evidence files; raw records and screenshots are not committed.

## Retained failures and local fixes

| Trial / source | Status | Evidence-backed cause and action |
| --- | --- | --- |
| `browser-01`, `d3bc7ca` | FAIL | New test clicked mobile-only Course materials tab on desktop; desktop already has persistent left reader. Corrected locator only. |
| `browser-02`, `e1b3a09` | FAIL | New fault handler removed its route before aborting the response; Playwright reported route already handled. Kept a one-shot handler active; independent local HTTP check passed. |
| `browser-03`, `d58ebf0` | Intentionally stopped; harness exit 1 | Prior PG snapshot showed exactly one card, so Good correctly empties the queue. Stopped only verified owned harness to revise the new scenario: restore empty state, explicitly create second deck, then inject loss. Reason in `browser-03-cancellation.txt`; normal cleanup passed. |
| `browser-04`, `29d3e8a` | FAIL | Restored counts matched, but comparison mixed rendered `innerText` newlines with adjacent-node `textContent`. Used consistent DOM text for both sides, retaining counter assertions. |
| `browser-05`, `990662f` | PASS | All 12 checks, PG export, no-real-provider proof and cleanup passed. |

No product bug was established by these script failures. No answer, scoring
requirement, frozen hash, baseline or failure record was changed to obtain PASS.

## Boundaries and stopping point

The two-second single-cue synthetic course is intentionally small. It validates
product mechanics and source-navigation plumbing, not realistic course diversity,
nonzero timestamp precision, multilingual teaching, ASR, or citation semantics.
Independent human agreement, learning outcomes and this task's real-model quality
are **NOT_RUN**. Existing historical real-model evidence is unchanged and is not
upgraded by this Mock result. No real model, external embedding/reviewer, paid run,
holdout evaluation, scale evaluation, cost optimization or CI work was performed.
Model connection management, real-provider UI, long recordings and upload-browser
flows are outside this bounded acceptance. No deployment or release was attempted.

Only local acceptance assets and this report/summary are committed. Other worktrees,
manual records, original evaluation data/results, product defaults and CI remain
untouched. The task ends here with all newly owned temporary services stopped and
evidence retained; no next evaluation batch is scheduled.
