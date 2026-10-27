# P8 offline implementation report — 2026-10-27

Implemented on `codex/p8-tutor` in its isolated worktree, based on P7 real-eval `e1e7af2`. No real provider calls, push, PR, merge, deployment, private env-file access or online configuration changes. Deterministic checks do not establish teaching quality.

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

Live Flash/Pro evaluation is **NOT_RUN**. Product provider remains Mock only and opt-in; source relevance, semantic support, context interpretation and Socratic teaching effectiveness remain unverified with real models. Fixed abstention text is a deliberately strict output protocol. The extractive summary is lossy; persistent budgets/deadlines can terminate long conversations/turns. Snapshot page slots are not media timestamps. No deployed stack/browser E2E, automatic grading, long-term learner memory or review scheduling was claimed. The live command is documented only, with dual opt-in, isolated DSN, frozen inputs, no retries and $0.70/400-call hard caps.

After all verification, only this task's PostgreSQL container was stopped; its volume, ledgers and all ignored outputs were retained for review.
