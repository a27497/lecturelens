# Repository closeout

`main` contains the two preserved Recruiter Demo commits, explicit Bailian ASR preparation, patched frontend dependencies and the CI-only MinIO source build. Repository organization does not deploy a new Agent or alter online model routing.

Evidence hydration/Authority changes, Multi-turn Study Agent, the independent explanation UI and their evaluation records belong to `exp/multiturn-relations-20261003`. Its frozen `candidate-7` remains **DEVELOPMENT_GATE_FAILED / unreleased**. Mechanism tests do not change that quality conclusion; no new real-model trials or held-out courses were consumed.

## Stable commit boundaries

- Recruiter Demo: `24fa878e92cfb22c9c453c2b283bb896e80bb6f8` and `90be6d8e1cfba1988d46d463a8d9fac4114aafdf`, unchanged history.
- Bailian ASR: `29f69a27251618f33e0b1e9bc29411190fd806a9`, also identified by local ref `codex/asr-bailian-20261007`. Java provider/configuration, sanitized failures, transcription retry integration and [ASR deployment instructions](ASR_BAILIAN.md) are one dependency-complete change. It does not depend on experimental Evidence or Python Agent code.
- Frontend dependencies: `8268daa3b45c2af8c8376385ecf26dad50c4c9b4`, fixes the existing lockfile audit findings without changing application code. The preceding commits retain their original dependency versions; use the final stable branch for reproduction.
- MinIO CI availability: `af0a9fa92361c81e2afdb9e67b50d19573703cba`, builds official source at the original release commits for Mock E2E only. The implementation is included in `main` unchanged from the L2-verified commit; default deployment pins and product/E2E code are preserved.

## Verification

Recruiter Demo's first commit passed 94 frontend tests and build; its second passed 95 frontend tests and build. Stable Python passed **618 tests, 0 skipped** with a separate PostgreSQL/pgvector test container, Ruff lint/format and wheel build. ASR passed **1,449 Java tests, 0 skipped**, JAR packaging and isolated no-key Mock infrastructure E2E, including Flyway, upload/MQ/FFmpeg/ASR/translation, Evidence pagination/QA provenance, ownership and idempotent deletion. Patched frontend passed **95 tests**, type checking, production build and `npm audit` with zero reported vulnerabilities.

Secret/privacy review scans publication files and new commit contents. Only explicitly synthetic redaction fixtures and public model artifact SHA256 values receive exact-file/exact-match scanner exclusions; private configuration, model output and `.data` are excluded from Git. Local demo profiles reuse public example placeholders and are not suitable as production credentials.

An initial supplementary Mock E2E startup used the unchanged example MySQL URL and connected to the shared demo database. It stopped at its first database assertion before creating a test course; startup logs report that no migration was necessary. Its logs remain in private closeout evidence. All MySQL, Redis, MinIO and RocketMQ endpoints were then checked and redirected to the dedicated closeout instance; that run passed. This is separate from model-quality evaluation.

The complete Phase 1 archive was verified in place, without a new backup. All original dirty file hashes and both worktrees' ignored `.data` files matched it before splitting. Historical failed trials, candidate identity and private evidence remain unchanged. The older dirty ASR worktree and all existing refs are retained.

## Remote CI and infrastructure blocker

On 2026-10-07, remote CI passed Python/PostgreSQL, Java and Frontend on both runtime heads: [stable `0e93c4f`](https://github.com/a27497/lecturelens/actions/runs/37575434702) and [experiment `c4b4f1f`](https://github.com/a27497/lecturelens/actions/runs/37575436667). Both Mock E2E jobs failed before application packaging or execution because Quay denied access to the pinned MinIO image (`401 unauthorized`). These workflows are **failed**, not complete CI passes.

Anonymous authenticated manifest requests for the fixed MinIO server/client digests also returned 401 from Quay and Docker Hub; the matching official archived binary checksum endpoints returned 410. The successful local Mock E2E at that stage used existing cached images at the original pinned digests, leaving fresh vendor-image reproduction blocked. The CI-only source-build successor below resolves the CI bootstrap path; default vendor-image availability remains unresolved. All failed attempts are retained in private closeout evidence.

### 2026-10-07 successor: CI-only MinIO source build

On stable `main` at `fd8740949c5237f956d89daafa7636d52e5d3d92`, both original Docker pulls were reproduced: manifest HEAD requests returned **401 UNAUTHORIZED**. Anonymous authenticated manifest GET requests also returned 401 from both Quay and Docker Hub; both archived checksum URLs still returned **410 Gone**. The earlier failures above remain valid historical evidence.

MinIO's [official source-only distribution instructions](https://github.com/minio/minio#source-only-distribution) provide a reproducible alternative for this gate. CI Mock E2E explicitly loads [`compose.ci-minio.yml`](../compose.ci-minio.yml) and builds **official source at the same server/client release commits** with [`Dockerfile.ci`](../infra/minio/Dockerfile.ci). Official annotated release tags resolved to these immutable commits; independently downloaded official GitHub archives are checked against the following SHA256 values before extraction:

| Component / original release | Official source commit | Archive SHA256 |
| --- | --- | --- |
| MinIO / `RELEASE.2025-04-22T22-12-26Z` | [`0d7408fc9969caf07de6a8c3a84f9fbb10a6739e`](https://github.com/minio/minio/tree/0d7408fc9969caf07de6a8c3a84f9fbb10a6739e) | `7eb30a913fea30f18069abf194e1e78e4983b558cc526911ae1c11396a9859a5` |
| mc / `RELEASE.2025-04-16T18-13-26Z` | [`b00526b153a31b36767991a4f5ce2cced435ee8e`](https://github.com/minio/mc/tree/b00526b153a31b36767991a4f5ce2cced435ee8e) | `4cd13e34daeeb8481c3ba8686b082f161b8dc1f7aad52d715a706a587349c6ae` |

The build also pins the official Docker Library [Go 1.24.2 Bookworm](https://hub.docker.com/_/golang) and [BusyBox 1.37.0 musl](https://hub.docker.com/_/busybox) multi-platform image digests. Go uses the original module files, checksum verification and a read-only module build, with automatic toolchain downloads disabled. These source-built binaries are identified as `DEVELOPMENT` with their exact commits; byte identity with vendor binaries is not claimed. Both images include the upstream AGPL license, NOTICE and third-party CREDITS. No third-party MinIO image is used.

**Cold availability evidence:** a newly created Docker-container BuildKit builder, `lecturelens-minio-cold-final-20261007`, reported **Total: 0B** before the final `--pull --no-cache` build. Its independent store downloaded all pinned Go/BusyBox layers and both official source archives; both archive hash checks and both `go mod verify` steps passed. The final build completed without cached build steps, and both binaries reported the expected release dates and commits. An initial build was stopped after discovering YAML timestamp coercion; the quoted timestamps and final Dockerfile were retested from the new empty builder. Existing cached vendor MinIO images were neither build inputs nor runtime images for this validation.

**Local validation passed:** the original infrastructure startup and HTTP Mock E2E scripts were copied byte-for-byte into an isolated reproduction directory, using only synthetic configuration with explicit separate service URLs and ports. New volumes were created for `lecturelens-demo-minio-cold-20261007`; MySQL contained **0 application tables** before backend startup. The unchanged E2E passed RocketMQ client readiness, Flyway, upload/MQ/FFmpeg/mock-ASR/translation/artifacts, canonical Evidence pagination/QA citation provenance, ownership and idempotent durable deletion. Offline Maven packaging, Compose configuration, YAML/workflow and Compose-contract checks, shell syntax and `git diff --check` also passed. Diagnostic records remain outside Git under `/tmp/lecturelens-minio-cold-20261007/`. The dedicated validation stack, volumes and builder were removed after testing.

CI's additional build command is:

```bash
export COMPOSE_FILE=compose.yaml:compose.ci-minio.yml
cp .env.demo.example .env.demo.local
docker compose --env-file .env.demo.local build --pull --no-cache minio minio-init
```

The job retains its required status, dependencies, timeout, application E2E assertions and failure handling. The override changes only MinIO image construction, the server entrypoint and the HTTP healthcheck client; S3 service commands, credentials, buckets, ports, persistent volumes and initialization dependencies are preserved. Default deployment image pins and all product code remain unchanged. This resolves the MinIO availability blocker **for the CI source-build path**, as verified locally and remotely below; default image pulls remain blocked. No experimental branch content, deployment, real-model or paid-ASR calls were involved. This is execution/infrastructure evidence, not real-model task-quality evidence.

**2026-10-08 L1 audit:** the same local candidate was independently checked against `fd8740949c5237f956d89daafa7636d52e5d3d92`. Minimal corrections include copying the pinned upstream NOTICE/CREDITS into both images and guarding cleanup when setup fails before creating `.env.demo.local`. The AGPL-3.0-or-later label matches the upstream source headers; LICENSE, NOTICE and CREDITS were compared byte-for-byte with both pinned archives. Official annotated tags and archive SHA256 values were rechecked, and exported build-stage `go.mod`/`go.sum` files remained identical to the archives after download and compilation. A deliberately incorrect archive hash stopped the build before module processing.

A second new Docker-container builder, `lecturelens-minio-l1-20261008`, started at **0B**, with a **2 CPU / 6 GiB** limit. The final candidate's `--pull --no-cache` build downloaded the pinned base layers and official sources without cached build steps and completed in **356.85 s**; the server and mc module/build steps took **325.5 s** and **220.7 s**, respectively, in parallel. The actual MinIO/mc container image IDs matched these newly built images. This is a cold MinIO build and fresh application state test, not an entirely uncached host: other infrastructure images and offline Maven dependencies used the existing local cache.

The unchanged infrastructure and HTTP E2E scripts passed using synthetic configuration and new volumes for `lecturelens-demo-minio-l1-20261008`; MySQL had **0 application tables** before backend startup. Infrastructure readiness took **11.36 s**, offline backend packaging **4.82 s**, and the full Mock E2E **19.45 s**, including the original readiness, pipeline, Evidence/QA, ownership and durable-deletion assertions. Resolved Compose comparison, workflow YAML/actionlint, shell syntax, image identity/license checks and `git diff --check` passed. Cleanup was exercised both before environment-file creation and after an injected failure with a partial stack, removing all project containers, volumes and network. Local diagnostics remain outside Git at `/tmp/lecturelens-minio-l1-20261008/`; the audit stack, volumes and builder were removed.

L1 established local readiness; the subsequent L2 verification below establishes the hosted-runner result.

**2026-10-08 L2 remote verification:** [CI run `37665614360`](https://github.com/a27497/lecturelens/actions/runs/37665614360), push attempt 1, passed at exact commit [`af0a9fa92361c81e2afdb9e67b50d19573703cba`](https://github.com/a27497/lecturelens/commit/af0a9fa92361c81e2afdb9e67b50d19573703cba). Agent/Python/PostgreSQL passed **618 tests**, Backend passed **1,449 tests**, and Frontend passed **95 tests**, audit and build with zero reported vulnerabilities. The full Mock E2E passed all six original readiness, pipeline, Evidence/QA, ownership and durable-deletion checks on a fresh GitHub hosted Ubuntu runner with newly created volumes. Both source archive hashes and both module verification steps passed, with no cached build steps or vendor MinIO image inputs.

Actions step timestamps report **128 s** for MinIO source build and **16 s** for HTTP Mock E2E. The complete Mock job took **327 s (5 min 27 s)**, including FFmpeg installation, packaging and cleanup, about **27.3%** of its unchanged **20-minute** timeout. Successful-path cleanup took **21 s** and removed containers, all four project volumes and the network. No CI failures or correction commits occurred; diagnostic upload was skipped by its `failure()` condition, while the E2E ran in full. Remote failure, cancellation and timeout cleanup paths were not triggered and remain unverified. This result establishes CI infrastructure compatibility at that commit, not Study Agent real-model quality, vendor binary byte identity or default vendor-image availability.

## Reproduction

Follow the locked install and checks in [CI](../.github/workflows/ci.yml): `uv sync --locked`, Ruff check/format, pytest with `AGENT_TEST_DATABASE_URL` pointing to an independent `lecturelens_agent_test` database, `mvn test` and package, and `npm ci`, unit tests, audit and build. Use distinct ports and explicit full service URLs for supplementary Mock E2E; changing a database port variable does not override `MYSQL_JDBC_URL`.

No additional cloud-ASR transcription or real-model task-quality trial was run during closeout. Existing acceptance scope and known product limitations remain in the README and evaluation records.
