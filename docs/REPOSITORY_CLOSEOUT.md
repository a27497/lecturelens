# Repository closeout

`main` contains the two preserved Recruiter Demo commits, explicit Bailian ASR preparation and patched frontend dependencies. Repository organization does not deploy a new Agent or alter online model routing.

Evidence hydration/Authority changes, Multi-turn Study Agent, the independent explanation UI and their evaluation records belong to `exp/multiturn-relations-20261003`. Its frozen `candidate-7` remains **DEVELOPMENT_GATE_FAILED / unreleased**. Mechanism tests do not change that quality conclusion; no new real-model trials or held-out courses were consumed.

## Stable commit boundaries

- Recruiter Demo: `24fa878e92cfb22c9c453c2b283bb896e80bb6f8` and `90be6d8e1cfba1988d46d463a8d9fac4114aafdf`, unchanged history.
- Bailian ASR: `29f69a27251618f33e0b1e9bc29411190fd806a9`, also identified by local ref `codex/asr-bailian-20261007`. Java provider/configuration, sanitized failures, transcription retry integration and [ASR deployment instructions](ASR_BAILIAN.md) are one dependency-complete change. It does not depend on experimental Evidence or Python Agent code.
- Frontend dependencies: `8268daa3b45c2af8c8376385ecf26dad50c4c9b4`, fixes the existing lockfile audit findings without changing application code. The preceding commits retain their original dependency versions; use the final stable branch for reproduction.

## Verification

Recruiter Demo's first commit passed 94 frontend tests and build; its second passed 95 frontend tests and build. Stable Python passed **618 tests, 0 skipped** with a separate PostgreSQL/pgvector test container, Ruff lint/format and wheel build. ASR passed **1,449 Java tests, 0 skipped**, JAR packaging and isolated no-key Mock infrastructure E2E, including Flyway, upload/MQ/FFmpeg/ASR/translation, Evidence pagination/QA provenance, ownership and idempotent deletion. Patched frontend passed **95 tests**, type checking, production build and `npm audit` with zero reported vulnerabilities.

Secret/privacy review scans publication files and new commit contents. Only explicitly synthetic redaction fixtures and public model artifact SHA256 values receive exact-file/exact-match scanner exclusions; private configuration, model output and `.data` are excluded from Git. Local demo profiles reuse public example placeholders and are not suitable as production credentials.

An initial supplementary Mock E2E startup used the unchanged example MySQL URL and connected to the shared demo database. It stopped at its first database assertion before creating a test course; startup logs report that no migration was necessary. Its logs remain in private closeout evidence. All MySQL, Redis, MinIO and RocketMQ endpoints were then checked and redirected to the dedicated closeout instance; that run passed. This is separate from model-quality evaluation.

The complete Phase 1 archive was verified in place, without a new backup. All original dirty file hashes and both worktrees' ignored `.data` files matched it before splitting. Historical failed trials, candidate identity and private evidence remain unchanged. The older dirty ASR worktree and all existing refs are retained.

## Remote CI and infrastructure blocker

On 2026-10-07, remote CI passed Python/PostgreSQL, Java and Frontend on both runtime heads: [stable `0e93c4f`](https://github.com/a27497/lecturelens/actions/runs/37575434702) and [experiment `c4b4f1f`](https://github.com/a27497/lecturelens/actions/runs/37575436667). Both Mock E2E jobs failed before application packaging or execution because Quay denied access to the pinned MinIO image (`401 unauthorized`). These workflows are **failed**, not complete CI passes.

Anonymous authenticated manifest requests for the fixed MinIO server/client digests also returned 401 from Quay and Docker Hub; the matching official archived binary checksum endpoints returned 410. The successful local Mock E2E used the existing cached images at the original pinned digests. Fresh-environment infrastructure reproduction therefore remains blocked by image availability. Closeout does not substitute another image, change MinIO versions or relax the E2E gate. All failed attempts are retained in private closeout evidence.

## Reproduction

Follow the locked install and checks in [CI](../.github/workflows/ci.yml): `uv sync --locked`, Ruff check/format, pytest with `AGENT_TEST_DATABASE_URL` pointing to an independent `lecturelens_agent_test` database, `mvn test` and package, and `npm ci`, unit tests, audit and build. Use distinct ports and explicit full service URLs for supplementary Mock E2E; changing a database port variable does not override `MYSQL_JDBC_URL`.

No additional cloud-ASR transcription or real-model task-quality trial was run during closeout. Existing acceptance scope and known product limitations remain in the README and evaluation records.

## Experimental branch verification

This branch additionally preserves the Evidence, frozen `candidate-7` runtime, explanation Frontend and Eval/Docs groups. Final closeout checks passed **1,235 Python/PostgreSQL**, **1,465 Java**, **95 Frontend** and **15 offline Eval harness** tests, all with zero skips; lint, package/build and dependency audit passed. These results verify mechanics and packaging. **DEVELOPMENT_GATE_FAILED / unreleased** and the original failed quality trials remain unchanged. See [the separate closeout record](../eval/repository-closeout/verification.json); the historical candidate records were not rewritten.

The new experiment worktree shares access to the retained ignored evidence through links in its `.data` directory. The original evidence root stays in the primary worktree and in the verified Phase 1 archive; no failed evidence is copied into Git or replaced.
