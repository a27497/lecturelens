# CI

Pull requests use the diff from the first parent of GitHub's PR merge commit
to the merge commit itself. The classifier counts both paths in a rename.
The existing docs-only exclusions still apply to PRs and pushes to `main`.

| Change | Jobs |
| --- | --- |
| Only `.md`, `.json` or `.jsonl` under `eval/`, outside the fixture directories below | Changes runs the routing tests and classifies the PR. |
| Only those eval file types, with at least one change under a fixture directory | Changes and Eval Fixtures run. Eval Fixtures uses isolated pgvector databases and deterministic providers. |
| Any other PR diff, any CI-triggering push to `main`, or a default manual run | Changes and the full checks run. |

## Eval fixture readers

| Paths under `eval/` | Tests |
| --- | --- |
| `feedback-v1/` | Feedback evaluation |
| `p7-real/`, `p8-tutor/` | Historical manifests, Mock evaluation runners, Tutor snapshot and citations |
| `retrieval-phase-a/`, `retrieval-v2/` | Retrieval benchmarks and Tutor citation grammar |
| `reviewer-probe/` | Reviewer probes |
| `source-support/` | Source-support fixtures |
| `tool-resilience-20261014/`, `tool-resilience-latency-20261014/` | Saved Study metrics batches |

When a test starts reading another eval directory, update the classifier and
the Eval Fixtures test selection in the same change.

## Full checks

- **Agent Service Test** runs the process-supervisor tests, Ruff checks and full
  Agent pytest suite with pgvector.
- **Backend Test** runs the Maven tests with MySQL and uploads the packaged JAR.
- **Frontend Build** runs unit tests, tests the npm audit gate, audits the lockfile
  dependencies and builds the frontend.
- **Pinned MinIO Images** supplies the two source-built images to both E2E jobs.
- **MySQL migrations and Mock AI E2E** uses an empty MySQL stack and runs the
  HTTP migration and Mock AI smoke tests.
- **Mock learning path (desktop and 390px)** runs the demo stack tests, seeds a
  separate course stack and runs Playwright in both viewports. Both E2E jobs can
  start as soon as the tested JAR and images are ready.

A manual dispatch with `eval_diff_commit` classifies the specified existing
commit's first-parent diff, which must qualify for an eval route. If fixtures are
selected, the tests run against the checkout of the dispatched ref. Leave the
input empty for full CI.

## Caches and rollback

MinIO's key covers the runner OS and architecture, both Compose files, the demo
env example and the image build directory. On a miss, CI builds once and shares
the image archive with both E2E jobs. The official source commits and archive
SHA-256 checks, builder and runtime image digests, and Go module checks apply to
every build. These pins identify the build inputs, so CI can reuse an archive for
the same key. There are no fallback keys.

The Playwright browser cache uses OS, architecture, runner distribution and the
locked `playwright-core` version. The Playwright installer fetches Chromium on a
miss and installs its system dependencies on every run. The backend JAR is an
artifact of the current run's Backend Test job.

Revert the workflow change to restore full checks on eval PRs and independent
image and JAR builds in the original serial E2E jobs.
