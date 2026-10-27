# P8 offline implementation report — 2026-10-27

Implemented on `codex/p8-tutor` in its isolated worktree, based on P7 real-eval `e1e7af2`. The original implementation work made no real provider calls, push, PR, merge, deployment, private env-file access or online configuration changes. The later authorized live failure and offline fix are recorded below. Deterministic checks do not establish teaching quality.

## Delivered areas

| Area | Files / behavior |
| --- | --- |
| Python | New `agent-service/src/lecturelens_real_eval/tutor/{contracts,store,runtime,app}.py`: course-scoped sessions/turns, bounded model-selected evidence tools, inline citation rejection, explicit abstention, Socratic prompts/reply feedback, window/summary, persistent budgets/cancellation, response/observation checkpoints, stale/deletion fences. Tutor lives under the already packaged unfrozen namespace; frozen Agent package and `pyproject.toml` unchanged. |
| Java | `TutorController.java` and gateway-only additions to `StudyTransport.java`; server identity/revision and permission checks before/after forwarding. `TutorControllerTest` / `TutorTransportTest`; no business schema changes. |
| Frontend | `api/tutor.ts`, `CourseTutorPanel.vue` and 17 panel tests; workspace/nav/location wiring in existing course view. Saved chat, Socratic toggle, source chips using existing seek guard, abstention/error/cancel/retry states and stale-response fencing. |
| Eval | `lecturelens_real_eval/tutor_channel.py`, `tutor_runner.py`; `eval/p8-tutor/` scripts, frozen inputs/thresholds, sample exporter and own compose definition. |
| Docs | P8 guide, root/service README, API, architecture, schema, deployment, product-contract/P7 pointers, env example and eval index. |

Migration list: additive, idempotent `tutor_session`, `tutor_turn` plus scope/uniqueness/one-active-turn indexes at Tutor service initialization. Separate eval `p8_tutor_real_run`, `p8_tutor_real_event`. No MySQL/Flyway migration, no cross-service writes, no changes inside frozen `lecturelens_agent` or `eval/p7-real/`. P7 development identity verifier still validates all 60 modules. Original CostPolicy fake-only gate is unchanged.

## Verification

Only compose project `lecturelens-p8-tutor-20261027`, PostgreSQL `127.0.0.1:25731`; Java's local fake HTTP server uses `25732`. Database tests are not skipped. Commands run from the worktree root:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25731/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25731 --network-records .data/p8-tutor/checks/packaged-full-network \
  -- -q --junitxml=../.data/p8-tutor/checks/packaged-full.xml

mvn -B -o -f backend/pom.xml \
  -Dtest=TutorControllerTest,TutorTransportTest,StudyControllerTest,StudyAuthorityTest test

npm run test:unit --prefix frontend
npm run type-check --prefix frontend
npm run build --prefix frontend
uv run --project agent-service --offline ruff check agent-service
uv run --project agent-service --offline ruff check eval/p8-tutor
git diff --check
```

Java: **28 passed, 0 skipped** (6 Tutor controller, 1 Tutor transport, 9 Study controller, 12 authority). Frontend: **282 passed / 43 files**, including **17 Tutor panel** tests; type-check and build pass. The existing large-bundle warning remains. Python full suite: **993 passed, 0 failed/errors, 0 skipped** in 556.54 seconds, including **53 new P8 mechanism cases** (30 runtime/app, 23 eval/channel), real PostgreSQL persistence and fake-transport evaluation. The only Python warnings are upstream Starlette/AnyIO and cryptography certificate deprecations. Ruff and whitespace checks pass. The distributable wheel includes the Tutor app/store without changing P7-frozen package metadata.

The Python launcher clears provider configuration and installs an inherited network audit fence before importing pytest. It allows this DB and local fake test servers; external egress is denied. Network counters and JUnit records remain under ignored `.data/p8-tutor/checks/`. Unit tests simulate invalid policy/configuration values without dispatching a real request. The standalone final mock run also used the socket fence and a clean environment with no provider credential/switch.

## Mock evaluation

Final run `p8-mock-packaged-20261027`, manifest digest `eabc04dc842c26dbe6b28880c2e7067f96853ed08e99e6ab546a29293a1605ba`:

- **PASS — NOT_RUN_MOCK_MECHANICS_ONLY**; 24 dialogues, 80 learner turns, 80 fixed mock reviews.
- 240 fake requests, 0 pending, 0 protocol failures; PG and append-only JSONL events exactly match. A final `--check-ledger` invocation returned the same calls/cost, with no blocked state.
- Citation verifiability, abstention, fixed-review support/context/Socratic metrics all 1.0. The latter are mock assertions, not model-quality evidence.
- p95 turn latency **1.801 s**; simulated accounting **$0.063168**, real spend **$0**.
- Outputs in `.data/p8-tutor/p8-mock-packaged-20261027/`: `dialogues.jsonl`, `reviews.jsonl`, `summary.json`, executable `sample.py`. `sample.py -n 5` was exercised with cited page/source text.

Actual mock invocation (with the clean environment/network fence described above):

```bash
uv run --project agent-service --offline python eval/p8-tutor/run.py \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25731/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/packaged-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-mock-packaged-20261027
python3 .data/p8-tutor/p8-mock-packaged-20261027/sample.py -n 5
```

All `algorithms-l1..l3`, `probability-l1..l3`, `quantum-l1..l2` have dialogues `-1/-2/-3`. All 24 include context follow-ups (56 such turns). Each `-3` has a fourth, related insufficient-evidence turn (8 total), with lecture-specific zero-hit terms retested. All eight `-2` dialogues use Socratic mode (24 turns), including next-turn learner reply feedback. Exact topics/absence terms are in the [README](README.md#scripts-and-negative-evidence) and frozen `dialogues.json`.

Development failures remain failures. The initial eval initialization defect and mathematical bracket/citation conflict were corrected before final freezing; their failed test records and the available failed mock trial remain under `.data/p8-tutor/checks/` and `development-failures/`. An earlier all-green mock belongs to its own earlier manifest identity and is not relabeled as this candidate. One broad regression was interrupted for final race/proposal checks. A subsequent broad run exposed P7's hash of package metadata; metadata was restored and Tutor moved into the existing packaged namespace. Neither partial run is counted as a complete pass; their JUnit/log records are preserved. P7 preflight and three targeted P7 regression checks then passed, and the built wheel was inspected for Tutor modules. Frozen thresholds were never relaxed.

## Remaining limits

The first live Flash/Pro trial aborted with the false positive recorded below; real-model teaching quality remains unverified. Product provider remains Mock only and opt-in; source relevance, semantic support, context interpretation and Socratic teaching effectiveness remain unverified with real models. Fixed abstention text is a deliberately strict output protocol. The extractive summary is lossy; persistent budgets/deadlines can terminate long conversations/turns. Snapshot page slots are not media timestamps. No deployed stack/browser E2E, automatic grading, long-term learner memory or review scheduling was claimed. The next live command is documentation only, with dual opt-in, isolated DSN, frozen inputs, no retries and $0.70/400-call hard caps.

After all verification, only this task's PostgreSQL container was stopped; its volume, ledgers and all ignored outputs were retained for review.

## Offline fix round 1

The separately authorized first live run `p8-real-review-20261027` ended **FAIL**, `REAL_EVAL_CITATION_FABRICATED`, after **2 real calls / $0.0039189**. The original `.data/p8-tutor/p8-real-review-20261027/dialogues.jsonl` records `Adj[u]` in the Flash answer: the old runtime/runner regex treated `u` as a source id. All 11 declared/inline ID references were valid for the lecture. This is an evaluator/contract false positive, not a fabricated source. The run directory and original accounting ledger remain untouched, and the historical FAIL is not relabeled.

Refrozen candidate **`p8-tutor-20261027-v2`** adds `tutor/citations.py` and changes only the runtime and runner citation parsing inputs. The grammar follows `eval/retrieval-v2/extract_corpus.py` and `build_cases.py` (snapshot ids and `-zh` translations), `CourseEvidenceService.java` (lowercase SHA-256 ids) and `study/context.py` (`eN` aliases). Both runtime inline matching and runner pre-schema inspection use it. The runner also checks every declared id regardless of syntax. Unknown or cross-lecture ID-shaped citations still block the ledger and fail the entire round, including malformed proposals. Runtime inline/declared equality, observed-selection membership, unique declared ids, authority re-READ and the exact abstention contract are preserved. Prompts, tools, dialogues and thresholds are unchanged; the latter two retain their original SHA-256 hashes in the manifest.

The public answer text is preserved exactly in `agent-service/tests/fixtures/p8_adjacency_answer.json` for offline regression. Tests exercise runtime acceptance with authority re-READ, all 11 valid references, unknown/cross-lecture citations in inline and declared fields before schema validation, mismatches in answer/evaluation, duplicate declarations and ordinary math brackets.

This fix round makes **zero real provider calls** and does not read private env files or enable live evaluation. Next live run: **`p8-real-review-20261027-r2`**, with new ledger **`ledger-p8-tutor-r2-20261027.jsonl`**. The [README command](README.md#exact-live-command-for-a-later-reviewer--do-not-run-in-this-task) is documentation only; r2 has not been executed in this fix round.

Candidate manifest SHA-256: `f0317d96b775a4d3d000ab8e072fd152de950cfa366d47c65bd161127ad8e9cf`. Only the new citation module and the changed runtime/runner input hashes differ from the previous manifest. Direct byte comparisons against the parent commit confirm unchanged `dialogues.json` and `thresholds.json`.

The first targeted fix run recorded **75 passed / 1 failed**: the new corpus-wide grammar check exposed the existing `-zh` translation suffix. That failure is retained under `.data/p8-tutor/checks/fix-r1-targeted.xml`; after including the source-defined suffix, the grammar checks passed **16/16** (`fix-r1-grammar.xml`).

Final offline verification uses the existing PG on `127.0.0.1:25731`, a fresh network-records directory, and the credential-clearing socket fence:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25731/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25731 --network-records .data/p8-tutor/checks/fix-r1-full-network \
  -- -q --junitxml=../.data/p8-tutor/checks/fix-r1-full.xml

uv run --project agent-service --offline ruff check agent-service eval/p8-tutor
git diff --check
```

Final full suite: **1,017 passed, 0 failures/errors, 0 skipped** in **352.27 s**, including **77 P8 tests** (33 runtime/app, 28 eval/channel, 16 citation grammar). This adds 24 cases to the original 993-test suite. PostgreSQL tests executed on the isolated project. Ruff and whitespace checks pass. The two warnings are the existing upstream Starlette/AnyIO and cryptography certificate deprecations. JUnit and network records are retained at the paths above.

The separate mock trial uses the same socket fence and a clean environment, run id `p8-mock-fix-r1-20261027`, local ledger `.data/p8-tutor/fix-r1-mock-ledger.jsonl` and output directory `.data/p8-tutor/p8-mock-fix-r1-20261027/`. No containers were started, stopped or removed during this fix round.

Mock result: **PASS — NOT_RUN_MOCK_MECHANICS_ONLY**, **24 dialogues / 80 turns / 80 fixed reviews / 240 fake requests**, 0 pending, 0 blocked, 0 protocol failures. All citation checks are valid; fixed mock support/context/Socratic/abstention metrics are 1.0. p95 Tutor latency: **0.623 s**; simulated accounting: **$0.063168**, real spend for this fix round: **$0**. A guarded `--check-ledger` returned identical 240-call accounting with matching PG/JSONL events; `sample.py -n 1` exported successfully. These results establish execution/protocol behavior, not real-model task quality.
