# P7 hardening-b offline verification — 2026-10-27

Candidate `p7-hardening-20261027-v2`, identity
`a7772a2204d7231693e5178570059b6323f8dbaa22bd2c1a69f30cdcced54837`.
Offline verification completed; **zero real provider calls**. The prior live
`p7-hardening-real-20261027` remains **PARTIAL** ($0.18845856, 137 calls):
confusable stops 2/8 and protocol failures 9/32. Its artifacts were read only.

The shared channel records ordered dropped tool names alongside counts, including
through the per-request hardening dispatch wrapper. Generation and review records
retain these observations even when validation fails. Only the first call is
executed; dropped calls are neither executed nor re-requested.

GraphAdapter offers only incoming create/stop schemas on generation call three,
rejects an empty terminal offering before dispatch, and still rejects call four.
A generic searching-model fixture now searches twice, sees only terminal tools,
stops on call three, and persists `stopped=true` with no CALL_LIMIT or cards.
This verifies execution mechanics; it does not measure real-model task quality.
The product graph, prompt, numeric store budgets, and double review are unchanged.

`--task-ids` validates the full freeze before selection and rejects invalid IDs
before touching a ledger. Focused metrics use selected-task denominators and the
same rate thresholds; ceiling the required correct-stop count avoids rounding a
small subset's minimum down to zero. The frozen eight-task minimum remains 7/8.
A focused run cannot satisfy the full 32-task completion gate or claim acceptance.
The 12-task focused Mock test completes with four cards, 48 fake calls, and the
expected PARTIAL full-suite verdict.

The successor freeze pins all 11 inputs, including the changed shared evaluator
modules. Other historical inputs and the development product identity remain
verified. Historical live preflight rejects the changed modules under its old
identity; historical mechanism tests explicitly use the verified successor pins.
All 32 tasks and all thresholds retain their exact HEAD bytes. No `eval/p7-real`
bytes or product package files changed.

| Check | Result |
| --- | --- |
| Full guarded Python/PostgreSQL suite | **996 passed, 0 skipped, 0 failed**, 331.78 seconds |
| Targeted evaluator suites | **109 passed, 0 skipped, 0 failed**; included in the full suite |
| Ruff | `ruff check agent-service eval/p7-hardening` passed; six edited Python files also passed format checking |
| Name-recording mutation | Removing the result field caused the new parallel-call test to fail with `KeyError: dropped_tool_call_names` |
| Last-call-filter mutation | Disabling the filter caused the new provider-schema test to fail because call three still offered search |

Each mutation ran one guarded test and produced exactly one expected failure;
both source files were restored before the passing full suite. The full suite's
two warnings are dependency deprecations from Starlette/AnyIO and certificate
parsing. Verification used PATH including `/home/dev/.local/bin`, only project
`lecturelens-p7-hardening-b-20261027`, and port **25722**. Its separate
`lecturelens_agent_test` database was created without deleting any volume.

Fresh records are under `.data/p7-hardening/checks/`: `full-b-v2.xml`,
`targeted-b-v2.xml`, mutation XML/log files, and distinct `network-*-b-v2/`
directories. The full suite's six Python audit records contain three database
connections, 75 ephemeral loopback test connections, and zero denied connections.
Native libpq connections do not increment Python socket audit counters. The
standalone Mock and ledger check also used the inherited socket fence. No
credential/env files were read or sourced and no shell live switch was enabled.

Standalone `p7-hardening-mock-b-v2-20261027` returned **PASS**:

- 32/32 tasks, 22 cards, 64 generation + 64 review fake requests (128 total).
- Synthetic ledger cost **$0.04608**; real provider cost **$0**.
- Citation validity, support, both negative stop rates, self-agreement, and
  near-duplicate agreement all 1.0; nine near-duplicate pairs.
- False-stop and protocol-failure rates 0; generation p95 **0.524239 seconds**.
- Independent mirrored ledger check: 128 calls, no pending calls, no block.

Artifacts and its ledger remain ignored under `.data/p7-hardening/`. Their
candidate and freeze hashes match the committed candidate inputs.

Changed files:

- `agent-service/src/lecturelens_real_eval/channel.py`
- `agent-service/src/lecturelens_real_eval/hardening_channel.py`
- `agent-service/src/lecturelens_real_eval/runner.py`
- `agent-service/src/lecturelens_real_eval/hardening_runner.py`
- `agent-service/tests/test_p7_hardening_eval.py`
- `agent-service/tests/test_p7_real_eval.py`
- `eval/p7-hardening/compose.yaml` (preserves the supplied port/volume isolation)
- `eval/p7-hardening/frozen.json`
- `eval/p7-hardening/README.md`
- `eval/p7-hardening/REPORT.md`

The exact next command is documented in the [README](README.md#next-focused-live-command--not-executed):
`p7-hardening-confusable-r2-20261027`, eight confusables plus four existing
definition controls, maximum $0.40 / 160 calls. **It was not executed.** This retry
uses consumed public-course tasks and cannot establish fresh holdout quality.
No push, PR, merge, deployment, or online configuration change was performed.
