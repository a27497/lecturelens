# Project direction

LectureLens is a course-grounded Study Agent project, currently experimental. The user's priority is Agent application engineering. Use [the product and architecture contract](docs/AGENT_PRODUCT_CONTRACT.md) when choosing the next implementation step.

## Ownership

- Put learning-task decisions, tool orchestration, context selection, Session/Run state, learning artifacts and future feedback/memory in `agent-service/` (Python).
- Keep Java responsible for authentication, course/media ingestion, authoritative Evidence/version/deletion checks, and the authenticated browser gateway. Change Java when an Agent capability or a concrete reliability defect requires it.
- PostgreSQL owns Agent execution state and derived indexes. MySQL owns course/business facts. Preserve ownership checks at tool boundaries; do not introduce cross-service writes to the other service's tables.
- Treat media ingestion as a deterministic preparation workflow. Treat ordinary course QA as a separate RAG path. Neither proves model-directed Agent behavior by itself.

## Feature acceptance

- For an Agent capability, identify the learner goal, model-selected tools, observations that affect the next decision, stored outcome, and failure/stop conditions.
- Keep tool calls bounded, authorized and replayable. Preserve cancellation, persistent budgets, version fences, idempotency and checkpoint recovery.
- Report execution/protocol tests separately from real-model task quality. Deterministic providers verify mechanics, not model intelligence.
- Preserve failed evaluation trials, frozen candidate identity and held-out data boundaries. Do not relabel evaluated incorrect outputs as successes to pass a gate.
- Frozen AU is the latest bounded Study Agent acceptance candidate: development goals 31/31 and fresh holdout goals 8/8 passed on known public courses, with 547 Python/PostgreSQL mechanism tests plus browser-loop, recovery, cancellation, ownership and deletion checks. It is not released; online configuration remains unchanged. See eval/phase-completion/FINAL_AU.md. This does not establish unseen-course generalization, automatic grading, long-term memory or review scheduling; future candidates need independent fresh holdout data.
- Prefer changes that improve the Agent learning flow, observations, context, tools or measured task outcomes. Backend-only platform expansion needs a concrete dependency in that flow.

## Verification and communication

- For Agent runtime changes, use meaningful Python tests and a separate PostgreSQL test database. Skipped database tests are not a complete pass. Follow the linked L2 documents for real-provider evaluation.
- Run checks appropriate to the changed layer; documentation-only edits do not require starting the service stack.
- Keep README, architecture and deployment instructions consistent with actual code. State implemented, experimental and planned capabilities separately. Current quality limitations remain visible when presenting the project as a Study Agent.
- Preserve existing uncommitted work. Keep provider credentials, downloaded media and private evaluation records out of Git.

## Documentation and comments

- Comments explain invariants, constraints, races, failure semantics or non-obvious trade-offs; preserve authority, idempotency, privacy and recovery explanations.
- Do not narrate obvious code execution.
- Public docs describe current behavior and link to evidence; experiment chronology belongs in `eval/` or history documents.
- Prefer concise engineering statements over tutorial-style prose and repeated caveats.
