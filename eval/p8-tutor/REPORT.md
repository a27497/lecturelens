# P8 offline implementation report — 2026-10-27

Current round: [`p8-tutor-20261027-v3` protocol hardening](#offline-protocol-hardening-v3) on `codex/p8-tutor-protocol`, using only port **25741**. The earlier sections below are historical records from the prior worktree/port, not commands rerun in this round.

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

## Offline protocol hardening v3

This round is on `codex/p8-tutor-protocol`, based on `970bd00`, in `/home/dev/projects/lecturelens-p8-tutor-protocol`. Only compose project `lecturelens-p8-tutor-protocol-20261027` and PostgreSQL **127.0.0.1:25741** were used. The supplied compose port/volume patch is preserved and pinned: volume key `p8-tutor-protocol-postgres`. `lecturelens_agent_test` was created on this instance; acceptance runs use its separate `lecturelens_agent_acceptance` DB. No original/sibling repository writes, frozen P7 changes, Java/MySQL changes, push, PR, merge or deployment.

The read-only r2 dialogue artifacts confirm citation formatting, repeated searches and missing follow-up evaluation failures. The historical `p8-real-review-20261027-r2` remains **PARTIAL**. Nothing in its proposals, scores, ledger or human audit was changed. This round makes **zero real provider calls**, reads nothing under `/home/dev/lecturelens-eval/` and reads no credentials, and does not execute a live command.

Changes:

- `tutor/runtime.py`: an observed citation-format mismatch or duplicate declaration becomes a structured error observation, atomically consumes a tool slot and checkpoints `ready`. A subsequent corrected finish can publish after authority checks. Unobserved IDs and authority re-READ failures remain fatal. Failed text is private and never published.
- At most two authoritative searches per turn, including empty searches. The committed observation journal supplies the persistent count. After two searches only finish is offered; a mock provider ignoring that restriction gets a search-limit observation and no additional authority SEARCH. Query results still receive authority re-READ, and publication keeps its CHECK/READ/fences. Four model/four tool limits, deadline, session budgets and exact abstention remain unchanged.
- The prompt and user payload flag required follow-up evaluation after a Socratic prompt. Missing/whitespace-only evaluation yields a repair observation; perpetual violations exhaust the existing budget without an answer. A supported Socratic finish must still ask a guiding question. Exact insufficient-evidence abstention still requires empty evaluation.
- `tutor_runner.py`: the eval adapter uses that same runtime. New `--dialogue-ids` validates unique known IDs before ledger/provider entry, preserves frozen script order and records scope/selected IDs. Focused runs cannot earn full-suite PASS, including when all 24 dialogues are selected.
- Tests cover failed-slot accounting, durable ready checkpoint/restart, corrected citations/evaluation, undeclared inline observed IDs, duplicate declarations, unrepaired budget exhaustion, fatal authority/Socratic violations, empty/nonempty search caps, and repairs through fake HTTP transport. Full-suite mock metrics are also checked against focused-scope denial.
- Current behavior/quality status updated in root README, product contract, architecture, P8 guide and eval README. Product remains opt-in Mock only; no real quality acceptance is claimed.

Freeze: **`p8-tutor-20261027-v3`**, manifest SHA-256 **`3e77cc62190a9830fc32c436f68be7549108795cd4b8c04a08720c5969089944`**. All 17 pinned files were hashed from final bytes. `dialogues.json` and `thresholds.json` are byte-identical to `970bd00`: citation/abstention 1.0, support ≥0.85, context ≥0.90, Socratic ≥0.75, protocol failure ≤0.05, latency ≤20 s, 400 calls / $0.70. No rate or cap was loosened. No dialogue/topic/lecture identity was added to runtime rules, and no held-out data was consumed.

### Commands actually run

Targeted Python/PostgreSQL check:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/protocol-targeted-network \
  -- -q tests/test_tutor.py tests/test_tutor_citations.py tests/test_p8_tutor_eval.py \
  --junitxml=../.data/p8-tutor/checks/protocol-targeted.xml
```

**92 passed, 0 failed/errors/skipped**, 60.17 s. After this run, the existing full-mock test was strengthened to assert that the same 24-dialogue/80-turn passing records cannot earn focused PASS; the final broad run below includes that assertion.

Broad guarded regression, excluding the seven legacy switch-setting cases:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/protocol-full-safe-network \
  -- -q \
  -k 'not (test_live_requires_both_switches or test_live_schema_failure_never_enters_chatprovider_repair or test_key_never_in_exception_logs_or_ledgers or test_parallel_tool_calls_execute_first_only_without_extra_request or test_parallel_tool_calls_with_unknown_tool_fail_closed)' \
  --junitxml=../.data/p8-tutor/checks/protocol-full-safe.xml
```

**1,025 passed, 0 failures/errors/skips, 7 deselected**, 335.96 s. All **92 Tutor tests** ran, including PostgreSQL runtime/app, citation grammar and real-eval Tutor fake-transport tests. Two existing upstream Starlette/AnyIO and certificate deprecation warnings remain. Complete selected-suite JUnit, stdout and network records are retained as `.data/p8-tutor/checks/protocol-full-safe.{xml,log}` and `protocol-full-safe-network/`. This is a broad selected-suite pass; the seven exclusions mean it is not an unrestricted full-suite result.

An initial unrestricted guarded run was interrupted after **304 passed** in 188.40 s: I discovered that five existing P7 test functions (seven parameterized cases) temporarily set the live opt-in and synthetic keys for fake-transport security checks. Those cases had already run; this test-local opt-in violates the stricter no-switch requirement despite using fake transport. The credential-clearing launcher and external-network fence were active, and **no real provider request occurred**. This interrupted run is not counted as a complete pass; its log/XML/network records are retained at `.data/p8-tutor/checks/protocol-full*`. The final broad command excludes these seven cases rather than modifying frozen/legacy tests. No live switches were set by the final command, its selected tests, targeted checks, mutations or standalone mock runs.

Mutation checks, with source restoration in `finally` after each:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-protocol-mutations.py
```

| Mutation | Selected regression | Result |
| --- | --- | --- |
| Raise immediately for observed citation mismatch | `test_citation_soft_rejection_checkpoints_slot_and_repairs_after_restart` | Exactly **1 failed, 0 errors/skips**, 0.45 s; missing repair checkpoint stops recovery |
| Disable cap (`MAX_SEARCH_CALLS = 99`) | `test_search_limit_forces_finish_and_rejects_ignored_limit[False]` | Exactly **1 failed, 0 errors/skips**, 0.48 s; third decision no longer offers only finish |

Evidence: `.data/p8-tutor/checks/protocol-mutation-{citation,search}.{patch,log,xml}`, corresponding `-network/` directories, and `protocol-mutations.json` (commands, counts, restored source digest). Both mutations were removed before the broad check and standalone eval. No mutant candidate was accepted or frozen.

Lint/format/whitespace commands passed:

```bash
uv run --project agent-service --offline ruff check agent-service eval/p8-tutor
uv run --project agent-service --offline ruff format --check \
  agent-service/src/lecturelens_real_eval/tutor/runtime.py \
  agent-service/src/lecturelens_real_eval/tutor_runner.py \
  agent-service/tests/test_tutor.py agent-service/tests/test_p8_tutor_eval.py
git diff --check
```

Java/frontend/browser checks were **not rerun** in this Python protocol round; those layers are unchanged. This is not real-model task-quality testing.

### Offline mock evaluation actually run

The retained `.data/p8-tutor/checks/run-guarded-tutor.py` launcher clears provider configuration and installs the same Python external-network fence before loading the CLI. It asserts that the startup guard loaded and writes network records to the supplied first argument. Actual full mock command:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/protocol-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/protocol-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-protocol-mock-20261027
```

**PASS — NOT_RUN_MOCK_MECHANICS_ONLY**: 24 dialogues / 80 turns / 80 fixed reviews / **240 fake requests**, 0 protocol failures, 0 pending/blocked. Citation/abstention and fixed-review support/context/Socratic metrics are 1.0. p95 turn latency **0.492 s**; simulated accounting **$0.063168**; real spend **$0**. Outputs: `.data/p8-tutor/p8-protocol-mock-20261027/{dialogues.jsonl,reviews.jsonl,summary.json,sample.py}`; captured stdout `.data/p8-tutor/checks/protocol-mock.log`.

The same guarded CLI with `--check-ledger` and a fresh `protocol-ledger-network/` directory returned exactly **240 calls / 63,168,000 nano-USD / 0 pending / no blocked state**, proving PG/JSONL agreement without provider dispatch. Command:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/protocol-ledger-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/protocol-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-protocol-mock-20261027 --check-ledger
python3 .data/p8-tutor/p8-protocol-mock-20261027/sample.py -n 1
```

Accounting stdout: `checks/protocol-ledger.log`; sampled source output: `checks/protocol-sample.txt` (both under `.data/p8-tutor/`).

A second **offline** CLI run exercised the exact focused selection proposed below, with a local ledger, no live flag and cleared provider environment:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/protocol-focus-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/protocol-focus-mock-ledger.jsonl \
  --max-usd 0.50 --max-calls 200 --run-id p8-protocol-focus-mock-20261027 \
  --dialogue-ids algorithms-l1-2 algorithms-l2-3 algorithms-l3-1 \
    probability-l1-2 probability-l2-2 probability-l3-2 quantum-l1-3 quantum-l2-3 \
    algorithms-l1-1 probability-l2-1 probability-l3-3
```

Result: **PARTIAL by scope**, no fatal error, **11 dialogues / 37 turns / 37 fixed reviews / 111 fake requests**, 0 protocol failures, all mock rates 1.0, p95 **0.467 s**, simulated **$0.0292152**. This confirms filter parsing and focused/full-suite separation, not acceptance or teaching quality. Outputs: `.data/p8-tutor/p8-protocol-focus-mock-20261027/` and `checks/protocol-focus-mock.log`.

### Exact next live command — NOT EXECUTED

For a separately authorized human operator with credentials and the required opt-in already configured in their shell. No private files were loaded by this round, and this block was not executed:

```bash
cd /home/dev/projects/lecturelens-p8-tutor-protocol
uv run --project agent-service --offline python eval/p8-tutor/run.py \
  --live \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger /home/dev/lecturelens-eval/deepseek-20261027/ledger-p8-protocol-focus-20261027.jsonl \
  --max-usd 0.50 --max-calls 200 --run-id p8-protocol-focus-20261027 \
  --dialogue-ids algorithms-l1-2 algorithms-l2-3 algorithms-l3-1 \
    probability-l1-2 probability-l2-2 probability-l3-2 quantum-l1-3 quantum-l2-3 \
    algorithms-l1-1 probability-l2-1 probability-l3-3
```

Eight r2 failing dialogues span citation/evaluation/search-budget failures, including the absent-topic budget case; three r2 passing dialogues are controls. This focused run can return PARTIAL at best. The full-suite frozen numeric gates remain unchanged.

Remaining risks: two searches may reduce recall; the existing four-call/deadline limits may still prevent repair when multiple independent mistakes occur. Unobserved IDs, authority changes and invalid abstention/Socratic outcomes remain fatal. Grounded evaluation, pedagogical quality and semantic support still need real-model measurement; deterministic reviewers establish no such quality. No unseen-course generalization, automatic grading, learner memory or scheduling is claimed. Conservative reservations may exhaust even the focused $0.50 budget before all turns complete. All historical failures and the initial interrupted broad check remain available.
