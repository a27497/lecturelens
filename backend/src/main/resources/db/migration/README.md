# Flyway migrations

These versioned migrations define the application schema. Enable Flyway for all runnable Demo and real deployments. Start an empty MySQL database by running the application with `FLYWAY_ENABLED=true`.

- Released migrations are immutable; add the next version for schema changes.
- Keep `validate-on-migrate` enabled and `baseline-on-migrate` disabled.
- Never repair, clean, or delete migration history automatically.
- The historical, private-development V21 recovery procedure is documented in `../../../../../../docs/LOCAL_FLYWAY_V21_RECOVERY.md`; it is not a deployment step.
- CI validates migrations against an empty MySQL database, independently of H2 unit tests.
- V25 adds USER/ADMIN roles and system model configuration foundations. Its version/audit immutability triggers require trigger-creation privileges; it does not switch AI providers. See [system model management](../../../../../../docs/SYSTEM_MODEL_MANAGEMENT.md).

V22/V23 introduce durable task boundaries and immutable evidence. Stop old workers before upgrading. V22 marks pre-upgrade in-flight tasks FAILED (`TASK_UPGRADE_INTERRUPTED`); retry creates a new task ID. Completed courses are preserved. See [the execution record](../../../../../../docs/C0_C3_EXECUTION.md).

- `R__course_qa_model_usage.sql` adds nullable exact QA execution/call references and dispatch state without advancing the V25 watermark. Pending PR #35 owns V26–V31. Preserve the repeatable filename/content after release; never repair history or enable outOfOrder to integrate it. Both integration orders are tested with pinned test-only #35 fixtures. See [model usage migration contract](../../../../../../docs/MODEL_USAGE.md#mysql-迁移与回滚).
