# Flyway migrations

These versioned migrations define the application schema. Enable Flyway for all runnable Demo and real deployments. Start an empty MySQL database by running the application with `FLYWAY_ENABLED=true`.

- Released migrations are immutable; add the next version for schema changes.
- Keep `validate-on-migrate` enabled and `baseline-on-migrate` disabled.
- Never repair, clean, or delete migration history automatically.
- The historical, private-development V21 recovery procedure is documented in `../../../../../../docs/LOCAL_FLYWAY_V21_RECOVERY.md`; it is not a deployment step.
- CI validates migrations against an empty MySQL database, independently of H2 unit tests.

V22/V23 introduce durable task boundaries and immutable evidence. Stop old workers before upgrading. V22 marks pre-upgrade in-flight tasks FAILED (`TASK_UPGRADE_INTERRUPTED`); retry creates a new task ID. Completed courses are preserved. See [the execution record](../../../../../../docs/C0_C3_EXECUTION.md).
