# Phase 1-E Tutor evaluation and offline checks

- [Frozen dataset](dataset.json) and [rubric](RUBRIC.md)
- [Proposed E3 limits and approval conditions](E3.md)
- [Local acceptance](REPORT.md)

Verify the freeze with `sha256sum -c SHA256SUMS` from this directory. Keep the original v19 review archive private and byte-identical. `diagnose.py` verifies the archive, pinned sources and coverage controls, and can inspect a case-to-turn PG journal export. If checking the exact upstream downloads, use the dataset's pinned raw Git paths and supply the resulting `sql.md`, `shell.md` and `git.md` files with `--upstream-dir`. `references.py` runs fixed Python, SQLite, POSIX shell and Git fixtures.

The tests require an isolated PostgreSQL with pgvector. The offline wrapper clears inherited configuration, guards Python connections to loopback and loads the source in this checkout. Copy the private archive into `.data/phase1e/v19-smoke-2227-REAL-review.zip` for the inherited Phase 1-D tests. Run under [the local check supervisor](../../docs/LOCAL_CHECK_EXECUTION.md), supplying the isolated `AGENT_TEST_DATABASE_URL` and the locked Agent Python environment.

`integration.py` reuses the Phase 1-D local Java, browser and Compose harness with fresh instance names, loopback services, cached local embeddings, and an offline-only HTTP adapter. It verifies canonical retrieval for each frozen packet before generation and compares the HTTP request digest against the PostgreSQL ledger in the separate synthetic end-to-end turn. The test grant mode cannot be used by the live factory. Keep the raw local evidence under `.data/`.

The fixture and offline results measure mechanics. Independent semantic review and any actual provider request belong to a separately authorized E3 trial.
