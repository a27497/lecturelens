# P8 offline implementation report — 2026-10-27

Current round: [`p8-tutor-20261027-v8` actionable finish-format repair](#offline-actionable-finish-format-repair-v8) on `codex/p8-tutor-protocol`, using only port **25741**. Earlier sections preserve historical candidates and their own worktree/port commands.

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

## Offline Finish-schema repair v4

This round adds one local commit above `585c98d` on `codex/p8-tutor-protocol`. It uses only the authorized compose project `lecturelens-p8-tutor-protocol-20261027`, PostgreSQL `127.0.0.1:25741`, the separate `lecturelens_agent_test` database and isolated acceptance schemas/ledgers. PostgreSQL is left running for the reviewer. No Java/MySQL, frozen P7, sibling worktree, deployment or online configuration changes were made. No push, PR or merge was performed.

The operator reports that `p8-protocol-focus-20261027` remains **PARTIAL**, with protocol_failure_rate **0.108** and four Finish-size failures: three proposals declaring 6–8 valid observed IDs and one 524-character evaluation after a Socratic prompt. Those historical artifacts and all earlier failures remain untouched; they were not rescored. This round made **zero real provider calls**, enabled no live switch, read no credentials or files under `/home/dev/lecturelens-eval/`, and used deterministic/fake transports only.

The learner goal remains a supported course explanation or feedback after a guiding question. The model chooses search and finish, sees an explicit size-error observation and chooses a corrected finish. Only that accepted proposal becomes the stored answer/evaluation/citations. Search, cancellation, version/ownership fences, idempotency, deadlines and persistent budgets retain their existing behavior.

Implementation:

- `tutor/contracts.py` defines a private `FinishProposal` that defers exactly three upper bounds while preserving strict types, required fields, identifier constraints, minimum text length and rejection of extra fields. The original `Finish` remains the advertised JSON schema and publication validator: **4 evidence IDs / 500 evaluation characters / 1,600 text characters**. Neither schema limits nor thresholds were relaxed.
- `tutor/runtime.py` checks every declared/inline ID against observed evidence and re-READs declared evidence before offering size repair. A size-only schema violation records `TUTOR_FINISH_LIMIT_EXCEEDED`, the exact limits and a resubmission instruction through `reject()` / `record_observation`. The observation and charged tool slot commit atomically at `ready`. The committed journal is the durable repair counter; restart or another search cannot reset it. A second size violation fails the turn with terminal `TUTOR_FINISH_LIMIT_EXCEEDED`. No extra call/tool slots or time are granted; exhausted budgets/deadlines retain their existing codes. Publication revalidates the original unchanged proposal against strict `Finish`. Nothing is truncated.
- `tutor_runner.py` validates against the private proposal schema only after its existing complete canonical citation scan. Other schema failures remain `REAL_EVAL_PROTOCOL_FAILURE`. `tutor_channel.py` continues validating all parsed parallel proposals after an earlier schema failure, so a fabricated citation in a later dropped call still durably blocks the round. Unobserved runtime IDs remain hard `TUTOR_CITATION_MISMATCH`.
- System instructions state all limits and the one-repair rule. Generic rules contain no dialogue, lecture or task IDs. The normal mock provider/transport is unchanged; tests inject malformed proposals around it.

Frozen candidate: **`p8-tutor-20261027-v4`**, manifest SHA-256 **`3a89e7a62e598a9e7ab82cb894865af8acb7ba3ce020478267ddb8da59952e8a`**. All **17** pinned hashes match final bytes. Direct comparisons with `git show 970bd00:<path>` confirm byte-identical `dialogues.json` (SHA-256 `8d8ca2b8f9ca0c04f433cc733eb3a663456fbdb956532cb0d23c79593b670fea`) and `thresholds.json` (`21d48ea5acd1fd63660fecd5ea03012aa5920ef048e0ff65430b68285be5b5da`). No caps changed, including the frozen **400 calls / $0.70** ceiling.

### Guarded verification

Targeted command actually run:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/schema-targeted-network \
  -- -q tests/test_tutor.py tests/test_tutor_citations.py tests/test_p8_tutor_eval.py \
  --junitxml=../.data/p8-tutor/checks/schema-targeted.xml
```

**124 passed / 0 failed/errors/skipped**, **70.90 s**, with one existing upstream Starlette/AnyIO deprecation warning. Coverage includes each individual limit and simultaneous limits; oversized evaluation after a Socratic prompt; a valid repaired finish published without changes; a second violation with and without restart; successful repair after restart without replay; model/tool/deadline exhaustion; authority failures preceding repair; strict non-limit schema/type failures, including invalid items beyond the fourth ID; and fabricated/foreign IDs in oversized declarations, inline evaluation and dropped parallel calls after an earlier schema failure. Focused fake-transport runs through `tutor_runner` repair each limit and remain **PARTIAL** by scope. Repeated size and non-limit schema failures remain failed turns and yield protocol_failure_rate **1.0**, rather than being relabeled successful.

Mutation command actually run:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-schema-mutations.py
```

| Mutant | Targeted regression | Result |
| --- | --- | --- |
| Fail immediately on the first size violation | `test_finish_limit_observation_then_unchanged_repair_publishes[ids]` | **Killed**, exactly 1 failed / 0 errors/skips |
| Allow unlimited size repairs after restart | `test_second_finish_limit_violation_is_fatal_even_after_restart[True]` | **Killed**, exactly 1 failed / 0 errors/skips |

Each mutant ran under `scripts/eval/check-study-offline.py` with the same isolated PG and network guard. The script restores source bytes in `finally`, checks their SHA-256, and records mutant/patch digests, exact commands and counts in `.data/p8-tutor/checks/schema-mutations.json`. Patches, logs, JUnit and network records are retained as `schema-mutation-*`; source was restored before broad verification and standalone mocks. Mutation stdout: `schema-mutations.log`. All paths are under `.data/p8-tutor/checks/`.

Broad selected-suite command actually run, after source restoration:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/schema-full-safe-network \
  -- -q \
  -k 'not (test_live_requires_both_switches or test_live_schema_failure_never_enters_chatprovider_repair or test_key_never_in_exception_logs_or_ledgers or test_parallel_tool_calls_execute_first_only_without_extra_request or test_parallel_tool_calls_with_unknown_tool_fail_closed)' \
  --junitxml=../.data/p8-tutor/checks/schema-full-safe.xml
```

**1,057 passed / 0 failures/errors/skips / 7 deselected**, **347.26 s**. The exclusions are the same seven P7 live-opt-in fake cases documented for v3; none was edited or executed in this round. All **124 Tutor cases** ran (55 runtime/app, 24 citation/schema, 45 eval/channel), adding 32 cases over v3. This is a broad selected-suite pass, not an unrestricted full-suite result. Two existing upstream Starlette/AnyIO and certificate deprecation warnings remain. Complete output/JUnit and network records: `.data/p8-tutor/checks/schema-full-safe.{log,xml}` and `schema-full-safe-network/`. No initial interrupted or failed verification run occurred in this round; mutant failures are intentional and separately recorded.

Lint, changed-file format and whitespace checks passed:

```bash
uv run --project agent-service --offline ruff check agent-service eval/p8-tutor
uv run --project agent-service --offline ruff format --check \
  agent-service/src/lecturelens_real_eval/tutor/contracts.py \
  agent-service/src/lecturelens_real_eval/tutor/runtime.py \
  agent-service/src/lecturelens_real_eval/tutor_channel.py \
  agent-service/src/lecturelens_real_eval/tutor_runner.py \
  agent-service/tests/test_tutor.py agent-service/tests/test_tutor_citations.py \
  agent-service/tests/test_p8_tutor_eval.py
git diff --check
```

Java/frontend/browser checks were not rerun; those layers are unchanged. These checks establish execution/protocol behavior, not real-model task quality.

### Standalone offline mocks

The existing `run-guarded-tutor.py` launcher clears provider configuration, installs the inherited external-network fence, and asserts guard startup before running the CLI. Full mock command actually run:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/schema-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/schema-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-schema-mock-20261027
```

Full mock result: **PASS — NOT_RUN_MOCK_MECHANICS_ONLY**, **24 dialogues / 80 turns / 80 fixed reviews / 240 fake requests**, 0 protocol failures, 0 pending and no blocked state. All fixed mock citation/support/context/Socratic/abstention rates are 1.0. p95 Tutor latency **0.413 s**; simulated accounting **$0.063168**, real spend **$0**. Outputs remain in `.data/p8-tutor/p8-schema-mock-20261027/`; stdout is `checks/schema-mock.log`.

A separate guarded `--check-ledger` with the same run ID, policy and local ledger returned exactly **240 calls / 63,168,000 nano-USD / 0 pending / no blocked state**, verifying PG/JSONL agreement without dispatch. Stdout: `.data/p8-tutor/checks/schema-ledger.log`; network records: `schema-ledger-network/`.

Focused mock command actually run:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/schema-focus-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/schema-focus-mock-ledger.jsonl \
  --max-usd 0.50 --max-calls 200 --run-id p8-schema-focus-mock-20261027 \
  --dialogue-ids algorithms-l1-2 algorithms-l2-3 algorithms-l3-1 \
    probability-l1-2 probability-l2-2 probability-l3-2 quantum-l1-3 quantum-l2-3 \
    algorithms-l1-1 probability-l2-1 probability-l3-3
```

Focused mock result: **PARTIAL by scope — NOT_RUN_MOCK_MECHANICS_ONLY**, **11 dialogues / 37 turns / 37 fixed reviews / 111 fake requests**, 0 protocol failures, no fatal error, 0 pending and no blocked state. All fixed mock rates are 1.0; p95 Tutor latency **0.402 s**; simulated accounting **$0.0292152**, real spend **$0**. Outputs: `.data/p8-tutor/p8-schema-focus-mock-20261027/`; stdout: `checks/schema-focus-mock.log`. The focused result is not full acceptance. The injected size-repair end-to-end tests above also remain focused PARTIAL; ordinary standalone mocks exercise the unchanged baseline transport.

All targeted, mutation, broad, full-mock, focused-mock and ledger launchers recorded **zero denied external connections**. They cleared provider configuration and enforced the startup socket fence. The complete final verification index is `.data/p8-tutor/checks/schema-verification.json`.

### Exact full-suite live command — NOT EXECUTED

For a separately authorized operator, with credentials and opt-in configured independently. This is the requested documentation-only command, with **no `--dialogue-ids`**:

```bash
cd /home/dev/projects/lecturelens-p8-tutor-protocol
uv run --project agent-service --offline python eval/p8-tutor/run.py \
  --live \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger /home/dev/lecturelens-eval/deepseek-20261027/ledger-p8-schema-full-20261027.jsonl \
  --max-usd 0.80 --max-calls 400 --run-id p8-schema-full-20261027
```

Constraint conflict: the requested `$0.80` exceeds the unchanged frozen `$0.70` policy ceiling. Current preflight rejects that argument before dispatch. The exact command is documented, but no cap was relaxed to make it executable; an operator must separately resolve that budget mismatch. This is the only task deviation/qualification. No live command was executed and no private ledger/env file was accessed.

Remaining risks: a real model may fail its single size repair or combine it with citation/evaluation mistakes; four calls/tools and the existing deadline may leave no recovery budget. A second violation still counts as a failed turn/protocol miss. Two searches can limit recall, and conservative reservations can exhaust the frozen spend cap. Fake transports and fixed reviewers prove mechanics only; grounded support, context retention, Socratic pedagogy and real-model protocol improvement remain unverified. No unseen-course generalization, automatic grading, long-term memory or scheduling is claimed. Historical failed/live records remain unchanged. The reviewer is responsible for stopping this round's still-running PG project.

## Offline unified Finish and Socratic repair (v5)

This round is offline only: deterministic providers and `httpx.MockTransport`, **zero real provider calls / $0 real spend**. It follows the unchanged v4 full live trial `p8-schema-full-20261027`: **PARTIAL**, 7/80 protocol failures (0.0875), 316 requests and $0.5276799. Five quantum turns exhausted their tool budget after repeated observed-ID declaration/inline mismatches; two supported Socratic turns returned `answered` and failed immediately. Size repair did publish two repaired turns. The local dialogue, summary and Grokbot audit records were read as evidence; none was modified or rescored. No private evaluation directory or credentials were accessed.

### Changes and bounded recovery

- Observed inline/declaration mismatches in either direction, duplicate declarations and any combination of the three size violations now share **one** `TUTOR_FINISH_REPAIR_REQUIRED` observation per turn. Structured fields and the message list `inline_not_declared`, `declared_not_inline`, duplicates and every offending actual size/exact limit. The instruction states: “the text/evaluation may cite only the declared evidence_ids, at most 4 unique ids; evaluation ≤ 500 characters; text ≤ 1600 characters; resubmit finish_tutor_turn”. A second format violation terminates with `TUTOR_FINISH_FORMAT_INVALID` and counts as a protocol failure. The committed observation journal is the counter; legacy `TUTOR_FINISH_LIMIT_EXCEEDED` and repairable `TUTOR_CITATION_MISMATCH` observations consume the same chance across restart.
- Supported Socratic turns must use `socratic_prompt` with `?` or `？`; supported non-Socratic turns must use `answered`. One independent, durable `TUTOR_SOCRATIC_REPAIR_REQUIRED` chance states the rule; repetition terminates with `TUTOR_SOCRATIC_CONTRACT`. Exact `insufficient_evidence` abstention remains exempt and unchanged. `TUTOR_EVALUATION_REQUIRED` retains its previous required-content check and ordinary-budget repair behavior; it receives no independent one-shot allowance or prepaid slot.
- Every declared and inline ID must be in observed `selected`, and the union is authoritatively re-READ **before** any repair. Unobserved IDs remain fatal `TUTOR_CITATION_MISMATCH`. The eval channel's existing canonical scan and durable `REAL_EVAL_CITATION_FABRICATED` block remain in force for unknown/cross-lecture IDs, including inline evaluation and dropped parallel proposals after earlier malformed proposals. The original strict `Finish` remains both the advertised tool schema and publication validator (4/500/1600); no IDs/text/evaluation/outcomes are silently changed. Runtime rules contain no dialogue/lecture/task IDs.
- Each new repair observation atomically commits the exact next request, its **prepaid model-call/token reservation**, the rejected tool slot and `ready` checkpoint under the existing fences. The request offers and accepts only `finish_tutor_turn`; it reports zero remaining searches. Dispatch consumes the prepaid reservation once, moves to `reserved` before provider entry, then checkpoints `received`. Recovery from `ready` sends once without recharging; recovery from an unresolved `reserved` call fails closed without resending. Counters, request and prepayment survive restart. Cancellation, authoritative version/deletion checks and the original persisted 20-second deadline still apply.
- The ordinary four-model/four-tool cap permits at most **one additional repair-only slot**, five total. Two searches + first finish + format repair + Socratic repair fit in five, in either repair order. The 64,000 turn-token, 60 session-call and 640,000 session-token caps are unchanged. If a cap prevents prepayment, `TUTOR_REPAIR_BUDGET_UNAVAILABLE` terminates **before issuing** a repair observation; it is a failed turn/protocol miss. Once issued, the next runtime call/tool capacity is reserved, so repair cannot itself yield `TUTOR_BUDGET_EXHAUSTED`. Authority, cancellation, deadline and the independently bounded eval ledger may still stop a repair.

### Budget math and metric scope

One repair after two searches uses **four** Tutor calls; both repair kinds use **five**. One review adds one channel request per completed turn. Across 80 turns, worst-case Tutor calls are **400**, or **480 requests including 80 reviews**. The unchanged run ledger still stops at **400 requests / $0.70**; worst-case completion is not guaranteed. No threshold, output size, search cap, token cap or deadline was relaxed. The only additional slot is the explicitly permitted fifth repair-only model/tool call.

A projection tied to the v4 trace assumes the five budget-failure turns now complete in the same four Tutor calls, the two Socratic failures each need one additional Tutor call, and all seven newly completed turns receive a review: **316 + 2 + 7 = 325 total requests**. At v4's overall mean cost, `$0.5276799 × 325 / 316 = $0.5427087585` (about **$0.543**), leaving 75 requests and about $0.157 to the caps. At the same mean, 480 requests would cost about $0.802, above both ceilings. These are illustrative estimates: longer prompts, repairs, reviewer usage and conservative byte reservations can stop the run earlier. No live request was made to validate the estimate.

`tutor_runner.summarize` now reports `metrics.over_abstain_count`, `metrics.over_abstain_rate`, and `over_abstain_turns` pairs `(dialogue_id, ordinal)`. The numerator counts **completed** `insufficient_evidence` turns whose script has `expected_insufficient=false`; the denominator includes **all attempted turns** with that false label, including failed turns. Empty denominator yields zero. This diagnostic adds no threshold and changes no verdict gate. The unit test covers completed, expected-negative, failed and Socratic cases, zero denominator and unchanged full-suite PASS eligibility.

**Union-bound dataset issue:** `probability-l1-3` turns **1–3** carry `expected_insufficient=false` but the probability-l1 corpus/snapshot contains **no union-bound evidence** (zero literal “union” hits). At v5 the dialogues were unchanged; the user-approved v6 correction below resolves this mismatch by expecting abstention on turns 1–3, while turn 4 already expects abstention and remains unchanged. Applying the new definition diagnostically to the read-only v4 dialogue file gives **5/72 = 0.0694444444**, at `probability-l1-3` ordinals 1, 2, 3; `quantum-l1-1` ordinal 2; and `quantum-l1-3` ordinal 2. This is not a rewritten historical summary or a judgment that those abstentions were wrong. The audit identifies the union-bound abstentions as reasonable behavior with a dataset risk.

### Final guarded verification

Frozen candidate: **`p8-tutor-20261027-v5`**, manifest SHA-256 **`dc63edaa83db4bff19c5a29426b144ff893e06bb5c45c1a5e28dc8e22ece1b9f`**. All **18** pinned hashes match final bytes, including the new reusable mutation runner. `git show 970bd00:<path>` comparisons confirm byte-identical dialogues (`8d8ca2b8f9ca0c04f433cc733eb3a663456fbdb956532cb0d23c79593b670fea`) and thresholds (`21d48ea5acd1fd63660fecd5ea03012aa5920ef048e0ff65430b68285be5b5da`). Frozen P7 files are unchanged.

Final targeted command actually run:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/repair-final-targeted-network \
  -- -q tests/test_tutor.py tests/test_tutor_citations.py tests/test_p8_tutor_eval.py \
  --junitxml=../.data/p8-tutor/checks/repair-final-targeted.xml
```

**148 passed / 0 failures/errors/skips**, **96.92 s**: 77 runtime/app, 24 citation/schema and 47 eval/channel cases. Coverage includes both mismatch directions with exact offending IDs; duplicates; simultaneous size/mismatch faults in one observation; unchanged publication after repair; second violations; restart and legacy journal counters; unobserved/authority failure before repair; fabricated/cross-lecture IDs and dropped parallel proposals; Socratic answered/missing-question and non-Socratic `socratic_prompt` repair; repeated Socratic violations; both repair orders after two searches (four/five calls); finish-only request and acceptance; reservation without double charge; capacity refusal before observation; deadline, unknown-call recovery, cancellation and authority fences on prepaid calls; unchanged evaluation and abstention contracts; and the report-only over-abstention metric. The fake-transport focused tests run through `tutor_runner` for **both repair kinds**, retain proposals and assert unchanged publication. Repeated format failures remain failed turns with protocol_failure_rate 1.0. One existing Starlette/AnyIO deprecation warning remains.

Final mutation command actually run:

```bash
uv run --project agent-service --offline python eval/p8-tutor/run-repair-mutations.py --label repair-final
```

| Mutant | Result |
| --- | --- |
| Immediate hard failure for a first size violation (previous schema mutant equivalent) | **Killed** |
| Silently truncate declared IDs to four and remove their inline references | **Killed** |
| Silently drop inline-undeclared references instead of repairing | **Killed** |
| Unlimited format repairs after restart (previous schema mutant equivalent) | **Killed** |
| Immediate hard failure for the first Socratic violation | **Killed** |
| Remove repair reservation, allowing the repair path to exhaust ordinary budget | **Killed** |
| Always report zero over-abstain count | **Killed** |

All **7/7** final mutants produced exactly **1 failed test / 0 errors/skips** each under `check-study-offline.py` on the separate PG test database. Each runner patches the intended source, runs a behavior-specific targeted test, restores bytes in `finally` and verifies source SHA-256. Restored runtime/runner hashes match the final frozen manifest. These are intentional test failures, not successful runtime/evaluation trials. The two original v4 schema mutants are replaced with the equivalents above; the old `.data` runner/evidence was not edited. Final commands, JUnit counts, patches, mutant/patch/restoration digests and network records are retained in `.data/p8-tutor/checks/repair-final-mutations.json` and `repair-final-mutation-*`. `--label` permits a fresh artifact prefix and refuses existing outputs.

Final broad selected-suite command actually run after restoration:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/repair-final-full-safe-network \
  -- -q \
  -k 'not (test_live_requires_both_switches or test_live_schema_failure_never_enters_chatprovider_repair or test_key_never_in_exception_logs_or_ledgers or test_parallel_tool_calls_execute_first_only_without_extra_request or test_parallel_tool_calls_with_unknown_tool_fail_closed)' \
  --junitxml=../.data/p8-tutor/checks/repair-final-full-safe.xml
```

**1,081 passed / 0 failures/errors/skips / 7 deselected**, **354.48 s**. All 148 Tutor cases ran. The same seven legacy P7 fake cases that internally set a live switch remain excluded; no frozen P7 asset/test was changed. This is a broad **selected-suite** result. Two existing upstream warnings remain (Starlette/AnyIO and certificate serial-number deprecation). The earlier `repair-full-safe.log` stopped during the model-capacity interruption and has no completed result; it is preserved rather than counted as a pass. Earlier completed targeted verification (145 cases before adding the three prepaid-boundary cases) and seven initial mutant kills are also retained. The final fresh logs/JUnit above are authoritative for this freeze.

Lint, changed-file format and whitespace checks passed:

```bash
uv run --project agent-service --offline ruff check agent-service eval/p8-tutor
uv run --project agent-service --offline ruff format --check \
  agent-service/src/lecturelens_real_eval/tutor/runtime.py \
  agent-service/src/lecturelens_real_eval/tutor_runner.py \
  agent-service/tests/test_tutor.py agent-service/tests/test_p8_tutor_eval.py \
  eval/p8-tutor/run-repair-mutations.py
git diff --check
```

Standalone full and focused mock commands actually run with the existing credential-clearing network-guard launcher:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/repair-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/repair-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-repair-mock-20261027

uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/repair-focus-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/repair-focus-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-repair-focus-mock-20261027 \
  --dialogue-ids algorithms-l1-2 algorithms-l2-3 algorithms-l3-1 \
    probability-l1-2 probability-l2-2 probability-l3-2 quantum-l1-3 quantum-l2-3 \
    algorithms-l1-1 probability-l2-1 probability-l3-3
```

| Standalone mock | Scope and result | Fake requests | Simulated accounting | p95 Tutor latency |
| --- | --- | --- | --- | --- |
| `p8-repair-mock-20261027` | **PASS**, 24 dialogues / 80 turns / 80 fixed reviews | 240 | $0.063168 | 0.561 s |
| `p8-repair-focus-mock-20261027` | **PARTIAL by focused scope**, 11 dialogues / 37 turns / 37 fixed reviews | 111 | $0.0292152 | 0.665 s |

Both are **NOT_RUN_MOCK_MECHANICS_ONLY**, with all fixed citation/support/context/Socratic/expected-abstention rates 1.0, protocol_failure_rate 0, `over_abstain_count=0`, `over_abstain_rate=0`, an empty diagnostic turn list, no fatal error, no pending calls and no blocked state. The baseline fake transport remains unchanged; injected malformed proposals are tested separately above. Both summaries record the final v5 manifest hash. Outputs remain in their named `.data/p8-tutor/<run_id>/` directories; stdout is `checks/repair-{mock,focus-mock}.log`. Mock accounting is not real spend.

A separate guarded `--check-ledger` using the full mock's same run ID, policy, candidate and local ledger (network records `repair-ledger-network`) returned **240 calls / 63,168,000 nano-USD / 0 pending / no blocked state**, exactly matching PG/JSONL accounting without dispatch. All final targeted, mutation, selected broad, full/focused mock and ledger runs recorded **zero denied external connections**. Consolidated counts, guard records, restored digests, unchanged-file digests and summaries are retained in `.data/p8-tutor/checks/repair-verification.json`. No live opt-in was set. No implementation deviation remains; the one extra repair-only slot and capacity-unavailable terminal path are the documented bounded design choices.

### Exact full-suite live command — NOT EXECUTED

For a separately authorized operator with credentials and opt-in configured independently. The requested full-suite command uses unchanged caps and no dialogue filter:

```bash
cd /home/dev/projects/lecturelens-p8-tutor-protocol
uv run --project agent-service --offline python eval/p8-tutor/run.py \
  --live \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger /home/dev/lecturelens-eval/deepseek-20261027/ledger-p8-repair-full-20261027.jsonl \
  --max-usd 0.70 --max-calls 400 --run-id p8-repair-full-20261027
```

Remaining risks: one repair can still be incorrect, a proposal can require both repair kinds, and the original 20-second deadline can expire before recovery. The fifth slot does not expand the independently enforced run/session/token budgets. Missing evaluation retains its older bounded behavior and can still exhaust the ordinary budget. Two searches can limit recall. Over-abstention labels include the documented corpus mismatch and have no acceptance threshold. Mock reviewers return fixed judgments: these tests establish protocol/execution mechanics, **not real-model task quality, semantic support or pedagogical improvement**. No unseen-course generalization, automatic grading, long-term memory or scheduling is claimed. No Java/frontend/P7 files, deployed configuration or historical trial records were changed. The isolated PostgreSQL project is left running; no push, PR, merge or deploy was performed.

## Offline controller-assembled citations v6

Candidate **`p8-tutor-20261027-v6`**, one local commit above `215b8ca`, on `codex/p8-tutor-protocol`. This round used deterministic providers / `httpx.MockTransport` only: **zero real provider calls / $0 real spend**, no live opt-in, private evaluation-directory access, push, PR, merge or deployment. Only compose project `lecturelens-p8-tutor-protocol-20261027`, port **25741**, was started and is left running. Existing `.data` trials were read-only; fresh verification labels start with `cite-`.

### Design and authority

The learner still asks a course question or replies to a guiding question. The model selects search, observes authorized evidence, chooses whether to search again, and submits text/evaluation/outcome. It now supplies citations only inline as `[id]`, at most four distinct IDs across both fields. `FinishInput` advertises no `evidence_ids`; `validate_proposal` discards that legacy field regardless of its type/value. A wrong, oversized, malformed or fabricated declaration cannot fail or pass a turn.

The controller uses the existing citation grammar, extracts text then evaluation in first-appearance order and de-duplicates without filtering candidates by availability. This becomes `Finish.evidence_ids` and orders the published canonical citation rows, independently of authority response order. Every extracted ID, including fifth and later IDs, must be in this turn's latest observed `selected` and pass authoritative READ **before repair**. Unobserved IDs remain fatal `TUTOR_CITATION_MISMATCH`; unknown/cross-lecture inline IDs durably block the eval ledger with `REAL_EVAL_CITATION_FABRICATED`, even in malformed/dropped parallel proposals. The source-ID grammar and ordinary math/index brackets are unchanged. `tutor_channel.py` needs no change: its existing all-proposal validation preserves that block after earlier malformed proposals.

More than four distinct IDs, evaluation over 500 characters and text over 1,600 characters share the existing durable one-shot format repair and prepaid reservation. Its observation lists `distinct_ids`, full ordered `evidence_ids`, explicit `excess_ids` beyond the first four, and actual sizes/exact limits. The model must resubmit finish; a second violation is `TUTOR_FINISH_FORMAT_INVALID`. Nothing is silently truncated, removed or rewritten. Only controller-assembled metadata plus unchanged model content can publish through the original strict `Finish` schema (4/500/1600). Supported finishes with zero inline IDs remain rejected; exact insufficient-evidence rules and non-limit type/schema validation remain. The independent Socratic outcome/question repair, evaluation requirement, restart counters (including legacy journal codes), cancellation/version/deletion fences and idempotency are preserved.

### Budget math

No new budget slot is introduced. Two searches + finish + format repair + Socratic repair still use at most **five Tutor calls / five tools per turn** under the original persisted **20-second deadline**. Repair atomically prepays its exact finish-only request before issuing the observation. Unknown dispatched calls fail closed; restart cannot reset or double-charge a reservation. Session/token caps, two-search cap and run caps **400 requests / $0.70** remain unchanged.

Across 80 turns, worst case is **400 Tutor calls + 80 reviews = 480 channel requests**, exceeding the independent 400-request run cap. The v5 full live run used **306 requests / $0.499732920** (about $0.500). If its eight failed turns complete in their existing Tutor call counts and each gains a review, the illustrative projection is **314 requests / $0.512797833**, leaving 86 requests / about $0.187. At the same overall mean, 480 requests would cost **$0.783894776**, exceeding both caps. Within four inline IDs, declaration differences no longer consume repair; actual five-plus-ID proposals still do. Different prompt lengths, review usage, conservative reservations or failed repairs can stop the run earlier. These estimates do not establish live improvement or guaranteed completion.

### Reviewer and reporting

The independent reviewer prompt now explicitly requires `context_retained=false` when a reply invents/assumes an antecedent after an immediately preceding failed/unpublished learner turn. Conversation history includes publication status/outcome. The runner also deterministically downgrades an answered context follow-up after such a turn, except an explicit clarification question. Exact abstentions and Socratic clarification questions are exempt from this additional downgrade. No false judgment is ever upgraded; no support/Socratic/abstention judgment is changed. Generic rules contain no dialogue/lecture/task IDs. Model review still covers invented antecedents outside this conservative deterministic rule.

The original `over_abstain_count`, `over_abstain_rate`, `over_abstain_turns` definition is unchanged: completed unexpected abstentions over all attempted `expected_insufficient=false` turns (including failed turns); zero denominator gives zero. Added `metrics.over_abstain_cascade_count` and `over_abstain_cascade_turns` identify the subset whose immediately previous turn failed/was unpublished. `metrics.over_abstain_non_cascade_count` and `over_abstain_non_cascade_turns` give the remainder. These diagnostics add no threshold or verdict rule.

### User-approved corpus correction (t44s14)

The probability-l1 lecture corpus/snapshot has no union-bound evidence; abstaining is correct. Only `probability-l1-3` turns **1, 2, 3** change: `expected_insufficient: false → true`, plus `zero_hit_terms: ["union"]`, exactly mirroring existing should-abstain entries. They now count in `no_evidence_abstain_rate`, not over-abstention. Turn **4** already expects abstention for the absent Dirichlet posterior extension and stays byte-identical, including its `zero_hit_terms: ["Dirichlet"]`. All learner text and every other field/turn/dialogue remain unchanged. This resolves the v5 dataset note; historical failed trials and summaries are neither rescored nor relabeled.

The fake transport now propagates an insufficient-evidence response to an elliptical “that”/“it” follow-up after an abstention, without task/lecture IDs or Tutor access to expected labels. Its reviews remain fixed judgments; this verifies mechanics only.

### Freeze and offline verification

Manifest SHA-256: **`6ad47af20b71f0f6e5eb98da3f84d33dd0b0954876590d6f095b7973331072d6`**. All **18** pinned hashes match final bytes, including the extended tracked mutation script. Dialogues are re-pinned to **`7a4965570a55720917b462640dd17b00eac99e890191c4ccdc3d05bfa840b512`**. Thresholds remain byte-identical to `970bd00`, SHA-256 **`21d48ea5acd1fd63660fecd5ea03012aa5920ef048e0ff65430b68285be5b5da`**. The dataset regression compares parsed JSON, hashes raw bytes outside the edited entry, and reconstructs the entire original file by reversing precisely the three approved field changes. Frozen P7 assets are unchanged.

Final targeted command:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/cite-final-targeted-network \
  -- -q tests/test_tutor.py tests/test_tutor_citations.py tests/test_p8_tutor_eval.py \
  --junitxml=../.data/p8-tutor/checks/cite-final-targeted.xml
```

**163 passed / 0 failures/errors/skips**, **88.15 s**: 78 runtime/app, 22 citation/schema and 63 eval/channel cases. One existing Starlette/AnyIO warning remains. Lint, changed-file format and whitespace checks pass.

Coverage includes ordered extraction/deduplication across both fields; publication order despite authority ordering; ignored wrong/superset/malformed declarations in runtime and fake runner; unobserved IDs before repair; fabricated/cross-lecture text/evaluation and dropped proposals; explicit excess lists; combined size/excess repair; repetition/restart/legacy counters; strict zero-ID rejection; Socratic repair; both repair orders after two searches; prepaid finish-only dispatch and capacity refusal; deadline/cancellation/version/unknown-call recovery; reviewer downgrade/exemptions/no upgrades; cascade split; exact dataset boundary; and fake-transport end-to-end runner behavior.

Mutation command:

```bash
uv run --project agent-service --offline python eval/p8-tutor/run-repair-mutations.py --label cite-final
```

| Mutant | Result |
| --- | --- |
| Silently drop unobserved candidates during extraction | **Killed** |
| Silently truncate extracted IDs to four | **Killed** |
| Trust provider-declared IDs instead of extraction | **Killed** |
| Unlimited format repairs after restart | **Killed** |
| Remove deterministic reviewer cascade downgrade | **Killed** |
| Always report zero cascade count | **Killed** |
| Immediately fail first size violation | **Killed** |
| Immediately fail first Socratic violation | **Killed** |
| Remove prepaid repair reservation | **Killed** |
| Always report zero total over-abstain count | **Killed** |

All **10/10** yielded exactly **1 failed test / 0 errors/skips** each under the network-guard launcher on isolated PG. Each patch is restored in `finally`, followed by byte/digest checks. The mutation manifest, exact commands, patches, JUnit/logs and restored hashes are `.data/p8-tutor/checks/cite-final-mutations.json` and `cite-final-mutation-*`. Intentional mutant failures are separate from successful verification.

Broad selected-suite command (same seven legacy P7 switch-setting cases deselected):

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/cite-final-full-safe-network \
  -- -q \
  -k 'not (test_live_requires_both_switches or test_live_schema_failure_never_enters_chatprovider_repair or test_key_never_in_exception_logs_or_ledgers or test_parallel_tool_calls_execute_first_only_without_extra_request or test_parallel_tool_calls_with_unknown_tool_fail_closed)' \
  --junitxml=../.data/p8-tutor/checks/cite-final-full-safe.xml
```

**1,096 passed / 0 failures/errors/skips / 7 deselected**, **375.06 s**. All 163 Tutor cases ran. The same seven legacy P7 fake cases that set a live switch were excluded; no frozen P7 case was modified. Existing Starlette/AnyIO and certificate serial-number warnings remain. This is a broad selected-suite result, not an unrestricted full-suite pass.

Lint/format/whitespace commands:

```bash
uv run --project agent-service --offline ruff check agent-service eval/p8-tutor
uv run --project agent-service --offline ruff format --check \
  agent-service/src/lecturelens_real_eval/tutor/{contracts.py,runtime.py,citations.py} \
  agent-service/src/lecturelens_real_eval/tutor_runner.py \
  agent-service/tests/{test_tutor.py,test_tutor_citations.py,test_p8_tutor_eval.py} \
  eval/p8-tutor/run-repair-mutations.py
git diff --check
```

Standalone full/focused mocks, through the existing credential-clearing startup network fence:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/cite-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/cite-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-cite-mock-20261027

uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/cite-focus-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/cite-focus-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-cite-focus-mock-20261027 \
  --dialogue-ids algorithms-l1-2 algorithms-l2-3 algorithms-l3-1 \
    probability-l1-2 probability-l2-2 probability-l3-2 quantum-l1-3 quantum-l2-3 \
    algorithms-l1-1 probability-l2-1 probability-l3-3 probability-l1-3
```

| Standalone mock | Result | Fake requests | Simulated accounting | p95 Tutor latency |
| --- | --- | --- | --- | --- |
| `p8-cite-mock-20261027` | **PASS**, 24 dialogues / 80 turns / 80 fixed reviews | 240 | $0.063168 | 0.484 s |
| `p8-cite-focus-mock-20261027` | **PARTIAL by scope**, 12 dialogues / 41 turns / 41 fixed reviews | 123 | $0.0323736 | 0.387 s |

Both are `NOT_RUN_MOCK_MECHANICS_ONLY`, with 0 protocol failures, all fixed citation/support/context/Socratic/expected-abstention rates 1.0, zero total/cascade/non-cascade over-abstentions, no fatal/blocked/pending state and the exact v6 manifest identity. The corrected union-bound dialogue abstains on all four turns in both mocks, with zero over-abstain flags. Outputs are under their named `.data/p8-tutor/<run_id>/` directories; stdout is `checks/cite-{mock,focus-mock}.log`. Real spend is **$0**.

A separate guarded ledger check returned **240 calls / 63,168,000 nano-USD / 0 pending / no block**, exactly matching the full mock PG/JSONL accounting without dispatch:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/cite-ledger-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/cite-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-cite-mock-20261027 --check-ledger
```

All 15 final targeted/broad/mutation/mock/ledger network-record groups have **zero denied external connections**. Consolidated verification is `.data/p8-tutor/checks/cite-verification.json`: JUnit counts, restored digests, all pinned hashes, exact unchanged strict Finish schema, unchanged thresholds/P7, precise dataset changes, mock summaries and ledger equality. The isolated compose project was confirmed running on 127.0.0.1:25741; it is left running.

Development verification is preserved separately: `cite-initial-targeted` recorded **135 passed / 25 failed**, mostly freeze-guard rejections after the pinned mutation script was edited during that run, plus an old uncited Socratic fixture and a new report test missing its required threshold key. Those fixtures were corrected; pinned inputs remained stable during subsequent runs. `cite-second-targeted` then passed **160/160** before the three final fake-runner integration cases were added. Neither initial failures nor historical live outputs were discarded or relabeled.

### Documented live command — NOT EXECUTED

For a separately authorized operator with credentials and opt-in configured independently; full suite, unchanged caps, no dialogue filter:

```bash
cd /home/dev/projects/lecturelens-p8-tutor-protocol
uv run --project agent-service --offline python eval/p8-tutor/run.py \
  --live \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger /home/dev/lecturelens-eval/deepseek-20261027/ledger-p8-cite-full-20261027.jsonl \
  --max-usd 0.70 --max-calls 400 --run-id p8-cite-full-20261027
```

Risks: a model can still exceed four inline IDs or fail its single repair, invent an unobserved ID, omit evaluation, or exhaust the unchanged deadline and independent budgets. Controller assembly removes duplicate metadata generation; it does not establish semantic citation support. Conservative deterministic clarification recognition cannot cover every wording/language; the reviewer prompt must enforce the broader antecedent rule. Mocks/fixed reviewers prove execution/protocol behavior, **not real-model quality, pedagogy or generalization**. No unseen-course generalization, automatic grading, long-term memory or scheduling is claimed. Java/frontend, frozen P7, deployment and historical records remain unchanged. No implementation deviation; the focused mock adds the corrected union-bound dialogue to exercise its new expectations.

## Offline context-retention rule v7

Candidate and evaluation protocol **`p8-tutor-20261027-v7`** supersede v6 for future runs. This is an offline scoring-rule correction: **zero real provider calls / $0 real spend**. V7 live quality is **NOT_RUN**, left for a later separately authorized operator run. Historical v6 trial files, reviews, summaries and the earlier sections of this report are unchanged; no historical result is relabeled or promoted to a pass.

### Rule and motivation

The operator-provided v6 audit reference, `p8-cite-full-20261027` / `human-audit.grokbot.json`, identifies false context penalties on clean insufficient-evidence follow-ups: `probability-l1-3` turns 2–4, `quantum-l1-1` turn 2 and `quantum-l1-3` turn 2. The reviewer prompt already exempted abstention/clarification after failed or unpublished turns, but v6 code only downgraded invented answers; it could not correct a false reviewer judgment. This task uses that audit description as motivation, without opening private evaluation records or rescoring the live trial.

`review_turn()` retains the existing deterministic downgrade: an answered context follow-up after an immediately preceding failed/unpublished turn is `context_retained=false`, except an explicitly recognized clarification question. It now also sets **only** `context_retained=true` for either an exact `ABSTENTION` answer with `outcome=insufficient_evidence`, or a clarification question matching the unchanged regex. This correction applies regardless of the previous turn's publication status, including chains of published abstentions. It does not upgrade invented answered follow-ups, accept nonexact abstentions, or change support, Socratic or `abstention_clean` judgments. The legitimate invented-antecedent failures identified in the audit (`quantum-l1-3` turn 3, `quantum-l2-1` turn 2, `quantum-l2-3` turn 3) remain subject to the downgrade.

`summarize()` is unchanged. All attempted `context_followup` turns remain in its denominator, including expected-insufficient turns. Failed/non-completed turns and missing/failed reviews remain misses. No diagnostic rescore is presented as an official result; new official quality scores require this freeze and a later live rerun.

V7 **inherits** v6/t44s14 should-abstain labeling: `probability-l1-3` turns 1–3 already have `expected_insufficient: true` and `zero_hit_terms: ["union"]`; turn 4 already expects abstention for Dirichlet. The entire dialogue file is byte-identical to v6. The existing regression still reconstructs the `970bd00` dialogue bytes by reversing only v6's approved three-turn correction; frozen input verification independently confirms the zero-hit terms.

Controller-assembled citations remain authoritative; provider `evidence_ids` remain ignored. Fabricated/unknown/cross-lecture inline IDs are fatal, including malformed/dropped proposals. More than four distinct inline IDs still requires the single durable format repair; no silent truncation or second repair is introduced. The citation parser, Tutor runtime, strict Finish schema, budgets, cancellation/recovery and authority fences are byte-identical to v6.

### Freeze

Full `frozen.json` manifest SHA-256: **`703a42e5a3b27f024e51ddf85eb526d79f1f208d5a84ad58df346e1bfb0e2c6b`**. The same **18** file paths are pinned as v6, with no additions; only `tutor_runner.py` and `run-repair-mutations.py` have new file digests. Thresholds are byte-identical to both v6/`ffe0cf7` and `970bd00`, SHA-256 **`21d48ea5acd1fd63660fecd5ea03012aa5920ef048e0ff65430b68285be5b5da`**. Dialogue SHA-256 remains **`7a4965570a55720917b462640dd17b00eac99e890191c4ccdc3d05bfa840b512`**. The manifest records candidate v7 and its byte digest is stored in every new mock policy/summary.

### Offline verification

All commands use the existing credential-clearing Python startup socket fence and only isolated PostgreSQL on **127.0.0.1:25741**, compose project `lecturelens-p8-tutor-protocol-20261027`, already running at task start. The separate test database is `lecturelens_agent_test`; mocks use `lecturelens_agent_acceptance`. No live opt-in was set.

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/ctx-v7-targeted-network \
  -- -q tests/test_tutor.py tests/test_tutor_citations.py tests/test_p8_tutor_eval.py \
  --junitxml=../.data/p8-tutor/checks/ctx-v7-targeted.xml

uv run --project agent-service --offline python eval/p8-tutor/run-repair-mutations.py --label ctx-v7
```

**172 passed / 0 failures/errors/skips**, **83.02 s**: 78 runtime/app, 22 citation/schema and 72 eval/channel cases. One existing Starlette/AnyIO deprecation warning remains. The nine new cases cross published-abstention/failed/unpublished priors with exact abstention/invented answer/nonexact abstention. They verify union-bound should-abstain context correction despite a false reviewer judgment, preservation of other judgment fields, denominator inclusion and failed-turn misses. The existing reviewer matrix now requires abstention/clarification/Socratic clarification to retain context regardless of reviewer bool; invented answers are still forced false and published/non-follow-up answers preserve reviewer values.

Existing citation tests are reused unchanged: fabricated/unknown/cross-lecture IDs in either field and dropped proposals remain fatal, provider declarations remain ignored, excess inline IDs require exactly one repair, and truncation/dropping cannot publish. All **11/11 mutants were killed**, each with exactly one failed test and zero errors/skips. This retains all ten v6 mutants and adds `context-non-penalty-removed`, which removes the new true assignment for abstention/clarification and is killed by the published-abstention follow-up regression. The pre-existing cascade-rule mutant is also killed by an invented-answer/reviewer-true case. Mutant failures are intentional negative evidence, separate from the passing test suite. The harness restored source bytes after every case; restored hashes and all 18 frozen hashes match. Fresh artifacts are `.data/p8-tutor/checks/ctx-v7-mutations.json` and `ctx-v7-mutation-*`; prior labels remain immutable.

Standalone mock commands (local ledgers only):

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/ctx-v7-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/ctx-v7-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-ctx-v7-mock-20261027

uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/ctx-v7-focus-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/ctx-v7-focus-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-ctx-v7-focus-mock-20261027 \
  --dialogue-ids algorithms-l1-2 algorithms-l2-3 algorithms-l3-1 \
    probability-l1-2 probability-l2-2 probability-l3-2 quantum-l1-3 quantum-l2-3 \
    algorithms-l1-1 probability-l2-1 probability-l3-3 probability-l1-3
```

| Standalone mock | Scope and result | Fake requests | Simulated accounting | p95 Tutor latency |
| --- | --- | --- | --- | --- |
| `p8-ctx-v7-mock-20261027` | **PASS**, 24 dialogues / 80 turns / 80 fixed reviews | 240 | $0.063168 | 0.389 s |
| `p8-ctx-v7-focus-mock-20261027` | **PARTIAL by scope**, 12 dialogues / 41 turns / 41 fixed reviews | 123 | $0.0323736 | 0.373 s |

Both are **NOT_RUN_MOCK_MECHANICS_ONLY**: all fixed citation/support/context/Socratic/expected-abstention rates are 1.0, protocol failure rate is 0, total/cascade/non-cascade over-abstention counts are 0, and fatal/blocked/pending state is absent. Both include `probability-l1-3`, with four completed abstentions and inherited expected-insufficient labels. Both record the exact v7 manifest hash. Outputs are under their fresh `.data/p8-tutor/<run_id>/` directories and `checks/ctx-v7-{mock,focus-mock}.log`. Mock accounting is simulated; real spend is **$0**.

A guarded `--check-ledger` with the full mock's same run ID/local ledger/caps returned **240 calls / 63,168,000 nano-USD / 0 pending / no block**, matching its summary without dispatch (`checks/ctx-v7-ledger.log`, `ctx-v7-ledger-network`). All **15** targeted/mutation/mock/ledger network-record groups have **zero denied external connections**. Consolidated evidence is `.data/p8-tutor/checks/ctx-v7-verification.json`, including JUnit counts, every mutant result/restored hash, unchanged-threshold byte comparisons against v6 and `970bd00`, unchanged dialogue bytes, the historical report-prefix check, all frozen hashes, both summaries and ledger equality.

`ruff check agent-service eval/p8-tutor`, changed-Python-file `ruff format --check`, and `git diff --check` pass. The v7 scope ran the targeted suite above; v6's historical broad-suite counts are not claimed as new v7 execution. Deterministic providers verify execution/protocol behavior only. **Live rerun NOT_RUN (left for operator)**; no real-model task-quality improvement is established. Conservative clarification recognition remains limited to the existing regex. The isolated PostgreSQL project is left running. No push, PR, merge, deployment, MEA/production/other-worktree changes, private record access or historical result rewrites were performed.

## Offline reviewer retry and suite continuation (v7)

The reported full live trials stopped when a short `deepseek-v4-pro` review tool call parsed but failed the `Review` schema. `Channel` correctly settled it as `failed` / `REAL_EVAL_PROTOCOL_FAILURE`; the runner then promoted any review exception to suite-fatal `REAL_EVAL_REVIEW_FAILED` and skipped remaining dialogues. Historical trials remain unchanged.

`review_turn` now retries only `EvalError` codes `REAL_EVAL_PROTOCOL_FAILURE` and `REAL_EVAL_REQUEST_FAILED`, with at most two extra requests (three total) for the same turn. Every request uses the existing ledger reservation/settlement and the same 400-call / $0.70 run caps. All success/failure review records contain integer `review_attempts`. Exhaustion writes one fail-closed record with `error=REAL_EVAL_REVIEW_FAILED`; missing quality judgments remain false and later turns/dialogues continue. Other review errors receive no retries. Blocked ledgers and hard `REAL_EVAL_` errors still stop the run, including budget/durability/citation failures. Tutor protocol failures receive no new retries, and citation extraction, fabrication rejection and one-shot excess-ID repair are unchanged.

Candidate identity remains `p8-tutor-20261027-v7`. Current manifest SHA-256: `a22f2b9e6af8d83c464e2200e14448de410d332a44b5f9eddb3b1ff40e433203`. Only runner and mutation-harness pins changed; all 18 pinned paths remain. `thresholds.json` is byte-identical to task-start tip `1768e85`.

Offline verification uses only the existing isolated PostgreSQL on `127.0.0.1:25741`, fresh acceptance schemas and the credential-clearing socket fence:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/review-retry-final-targeted-network \
  -- -q tests/test_p8_tutor_eval.py tests/test_tutor.py tests/test_tutor_citations.py \
  --junitxml=../.data/p8-tutor/checks/review-retry-final-targeted.xml

uv run --project agent-service --offline python eval/p8-tutor/run-repair-mutations.py --label review-retry
```

New integration cases cover two schema/request failures then third-attempt success, three failures followed by later turns and a second dialogue, unique review records, failed-call charges and mirrored ledger accounting, redaction, no retries for other errors, and a budget block during retry. Existing Tutor protocol/fabricated-citation tests are included. The mutation harness adds `review-retry-removed` and `review-failure-kills-suite`; it temporarily pins each mutant so integration tests reach its behavior, then restores and verifies source and manifest bytes.

An initial invocation was interrupted after 46 passes / 25 failures because the preceding manifest refresh used an unavailable `python` executable and left stale pins. Those failures were `REAL_EVAL_FROZEN_INPUT_CHANGED`; the corrected invocation above uses refreshed pins and separate artifacts. The interrupted run is not counted as completed verification.

**Live evidence pending / NOT_RUN; real provider calls 0, real spend $0.** The broad repository suite and standalone `run.py` smoke are NOT_RUN in this round; the targeted suite includes the full 24-dialogue / 80-turn mock integration. Deterministic tests establish mechanics, not model teaching quality. No push, merge, deployment, MEA, other-worktree or production-DB changes.

Corrected targeted result: **180 passed / 0 failed / 0 errors / 0 skipped** in **110.35 s** (80 eval/channel, 78 runtime/app, 22 citation/schema), with one existing Starlette/AnyIO deprecation warning. JUnit and log: `checks/review-retry-final-targeted.{xml,log}` under `.data/p8-tutor/`. The full mock integration completed 24 dialogues / 80 turns with 240 fake requests; retry cases completed both dialogues / all six turns with 20 fake requests, including exactly eight review requests and one review record per turn. Ruff check, changed-Python format check and whitespace checks pass.

Mutation result: **13/13 killed**, each with exactly one expected test failure, zero errors/skips. `review-retry-removed` fails the request-count assertion (18 vs 20); `review-failure-kills-suite` fails the PARTIAL/no-fatal assertion (FAIL instead). These reach the intended behavior rather than failing frozen-input validation. Results and restoration hashes: `.data/p8-tutor/checks/review-retry-mutations.json`; patches, logs, JUnit and network records: `review-retry-mutation-*`. Source and manifest bytes were restored and all 18 pins rechecked afterward. The 15 targeted/mutation network-record groups (including the interrupted launch) record **zero denied external connections**.

## Offline actionable finish-format repair (v8)

Candidate `p8-tutor-20261027-v8` addresses the eight `TUTOR_FINISH_FORMAT_INVALID` turns in the supplied v7 live trial `p8-ctx-v7-retry-full-20261027`. That trial's protocol failure rate was 0.10; all nine context misses arose directly or by cascade from these failures. Its results and original artifacts remain unchanged.

The earlier hypothesis that `[u]`/`[v]` were counted in this trial was wrong. The existing strict `assembled_citation_ids` regex already excluded `[u]`, `[v]`, `[A]` and `[x_1]`; its source bytes are unchanged in v8. Re-extraction from the supplied `dialogues.jsonl` gives:

| Failed turn | First strict IDs / text chars | Repaired strict IDs / text chars |
| --- | --- | --- |
| algorithms-l1-3 / 3 | 5 / 1318 | 5 / 1282 |
| algorithms-l3-1 / 3 | 6 / 1278 | 5 / 1268 |
| algorithms-l3-3 / 2 | 5 / 1557 | 4 / 1641 |
| quantum-l1-1 / 2 | 6 / 1358 | 5 / 1222 |
| quantum-l1-1 / 3 | 6 / 1404 | 5 / 1159 |
| quantum-l1-3 / 2 | 5 / 1744 | 4 / 1762 |
| quantum-l2-1 / 1 | 7 / 1348 | 6 / 1291 |
| quantum-l2-3 / 1 | 6 / 1273 | 5 / 1106 |

All these finishes had empty evaluation fields. Six repairs still contained 5–6 IDs; two reached four IDs but exceeded 1600 text characters. The model usually removed only one ID or failed to shorten enough. V7's count/limit reminder did not reliably elicit a valid resubmission.

The runtime system prompt and finish tool description now share actionable limits: prefer 2–3 distinct observed IDs, at most four across both fields, target text ≤1200 characters with the hard 1600 limit, evaluation ≤500, and parentheses for math. `TUTOR_FINISH_REPAIR_REQUIRED` adds ordered `keep_ids` (first four) and `remove_ids` (excess), retaining existing diagnostic fields. It tells the model to delete every removed inline citation in both fields and claims relying only on those sources, or re-attribute only when kept evidence supports them; introduce no new IDs; and resubmit only `finish_tutor_turn`. Overlength fields get actual character counts, required maxima and explicit rewrite targets. This is model guidance, not controller editing or an additional retry.

The learner goal and tools are unchanged: read course evidence, then produce a supported answer or guiding question, or stop with insufficient evidence. The repair observation can change the model's final selection and wording; the resubmitted answer/evaluation and controller-extracted ordered citations are stored transactionally only after validation. A second format violation still fails `TUTOR_FINISH_FORMAT_INVALID`; unauthorized/foreign IDs fail before repair, and the eval fabricated-citation ledger block remains fatal. Cancellation, authority/version/deletion fences, replay/recovery, prepaid repair budgets, context rules and reviewer retry are unchanged. Strict 4-ID / 500-evaluation / 1600-text limits remain intact; 1200 is only a generation target.

Changed files: `tutor/runtime.py`; `tests/test_tutor.py`, `test_tutor_citations.py`, `test_p8_tutor_eval.py`; minimal `tests/fixtures/p8_finish_v8.json`; mutation harness and frozen manifest; root README and this directory's README/REPORT. No other protocol version marker required updating: the `v7` source/config search found only the frozen candidate; historical v7 evidence and context-rule references retain their names.

The fixture stores only original strict ID order by field, character lengths, outcome/mode and math tokens from all eight failed first finishes. Synthetic padding replays format validation through the real runtime and isolated PostgreSQL checkpoints. Each valid fake repair uses only the kept IDs, changes their order and rewrites the text/evaluation; publication must equal that resubmission exactly, including ordered authoritative citation rows. Each fixture also runs with a second proposal exceeding IDs, text or evaluation, for 24 fail-closed cases. This is protocol/mechanism evidence, not semantic task-quality replay.

Verification commands (credential-clearing socket fence; only isolated PostgreSQL port **25741**):

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/finish-v8-targeted-network \
  -- -q tests/test_p8_tutor_eval.py tests/test_tutor.py tests/test_tutor_citations.py \
  --junitxml=../.data/p8-tutor/checks/finish-v8-targeted.xml

uv run --project agent-service --offline python eval/p8-tutor/run-repair-mutations.py --label finish-v8

# Repeat the targeted command with fresh finish-v8-final-targeted artifact names.

uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/finish-v8-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/finish-v8-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-finish-v8-mock-20261027
```

Both targeted executions passed **223 / 223 tests, 0 failures/errors/skips**: initial **111.94 s**, post-mutation rerun **123.58 s**. Each includes **84** eval/channel, **114** runtime/app and **25** citation/schema cases. One existing Starlette/AnyIO deprecation warning remains. Coverage includes math tokens in both fields without mismatch/fatal, strict foreign aliases/corpus IDs/hashes causing runtime mismatch and eval fatal blocks, exact repair diagnostics, no silent publication edits, all eight valid fixture repairs, 24 repeated-limit rejections, and existing restart/budget/cancellation/authority/context/reviewer-retry cases. JUnit/logs: `.data/p8-tutor/checks/finish-v8-{targeted,final-targeted}.{xml,log}`.

The full mutation set killed **16 / 16**, each with exactly one expected test failure and zero errors/skips. All 13 previous mutants remain; v8 adds `repair-keep-remove-missing`, `silent-truncate-excess-ids` (removes inline tokens and metadata before validation), and `math-bracket-counted` (disables strict candidate filtering). They fail respectively on missing repair data preventing completion, absence of the required model resubmission, and math text incorrectly failing publication. The harness temporarily refreshes each mutant's pin, then restores and verifies original source/manifest bytes. Evidence: `.data/p8-tutor/checks/finish-v8-mutations.json`, `finish-v8-mutations.log` and `finish-v8-mutation-*` patches/logs/JUnit/network records. These expected negative-test failures are separate from the passing targeted suite.

Standalone `eval/p8-tutor/run.py`, through the guarded wrapper and **without `--live`**, completed `p8-finish-v8-mock-20261027`: **PASS**, 24 dialogues / 80 turns / 80 reviews / 240 fake requests, protocol failures 0, all fixed quality rates 1.0, no fatal/blocked/pending state. Its quality status is **NOT_RUN_MOCK_MECHANICS_ONLY**. Accounting is simulated **$0.063168**, with **$0 real spend**; p95 turn latency **0.503 s**. Summary/dialogues/reviews are under `.data/p8-tutor/p8-finish-v8-mock-20261027/`; standalone log is `checks/finish-v8-mock.log`.

Manifest SHA-256: **`4e0cce141a6c6393e894b86b843ef3965fabd0ec71c92cb21e3f7a5812b9baa2`**. All **18** pins verify; only runtime and mutation-harness pins differ from v7. `thresholds.json` SHA-256 remains **`21d48ea5acd1fd63660fecd5ea03012aa5920ef048e0ff65430b68285be5b5da`**, byte-identical to task-start `d3e3253`. Dialogue scripts, strict extractor, contracts and eval runner are also byte-identical. All **19** targeted/mutation/mock network-record groups have **zero denied external connections**. Consolidated checks, fixture/source comparison, restoration hashes, JUnit counts and mock summary: `.data/p8-tutor/checks/finish-v8-verification.json`.

`ruff check agent-service eval/p8-tutor`, changed-Python `ruff format --check`, and `git diff --check` pass. **NOT_RUN:** real-provider/live v8 task quality; broad repository suite; Java/frontend checks (unchanged layers). Real provider calls **0**, real spend **$0**. The original failed trials retain their results; no new holdout was consumed. No push, deployment, MEA, other-worktree or production-database changes. The existing isolated PostgreSQL project remains running.
