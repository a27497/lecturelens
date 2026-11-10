# Phase 0 integration summary

The integration starts from `main` at `300be51`. It brings across selected
changes from the local Phase 0 candidate `17d7863` and keeps the existing
course workspace, Tutor protocol, flashcards and choice review.

- Java registers cancellation handles before submitting tasks and preserves the
  active handle when a duplicate task arrives. System-model diagnostics can
  record an unresolved model before routing selects one.
- The Study provider disables thinking for tool calls to the exact official
  DeepSeek endpoint with the supported model names. The Phase 0 source manifest
  identifies this development build. A source-only test fixture verifies the
  previous P10 identity without changing its frozen manifest.
- Frontend transitive dependency fixes retain the direct dependency versions.
  Browser checks cover the current course workspace controls and source-version
  protections. The development supervisor records cancellation and cleans up its
  own descendants.

Run the cross-service check with the public, pinned embedding cache described
in the [mock smoke prerequisites](../../scripts/ci/mock-study-tutor-e2e.md):

```bash
python3 scripts/dev/run_check.py --name phase0-learning-UNIQUE --timeout 900 -- \
  python3 eval/phase0-integration-20261108/learning_smoke.py \
  --output-dir .data/phase0/learning-UNIQUE \
  --embedding-cache-source /path/to/public-embedding-cache
```

The smoke uses disposable databases, synthetic accounts and Mock providers.
It exercises Tutor recovery and cancellation, flashcards, saved practice and
feedback, choice review and owner isolation. It enables the existing feedback
switch in its test stack only. These checks measure execution and protocol
behavior. Real-model teaching quality was outside this integration's scope.

## Original Phase 0 acceptance

The [original Phase 0 report](https://github.com/a27497/lecturelens/blob/17d78636cf97fcf55fe642b1ecc30c5e2ea48865/eval/phase0-integration-20261108/REPORT.md)
records the historical checks, unsuccessful attempts, and scope of acceptance.
The accompanying [check records](CHECKS.json) and [selection decisions](PR53_SELECTION.json)
are retained in this directory.
