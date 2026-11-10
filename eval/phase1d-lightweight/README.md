# Phase 1-D local acceptance

Read [comparison](COMPARISON.md), [candidate contract](../../docs/LIGHT_TUTOR.md) and [report](REPORT.md). The inherited Phase 0 CI remains PENDING. No real calls or historical authorization are used.

`run_offline.py` clears inherited credentials, inserts this checkout's source and restricts Python sockets to loopback. It expects this task's separate PostgreSQL at 127.0.0.1:25851 with the public synthetic test identity in that file. Tests create/drop unique schemas. Supply a byte-identical, private `.data/phase1d/failed-real-review.zip`; the test verifies SHA256 before loading it. Do not put private real responses in Git.

`integration.py` creates only new Compose projects, loopback ports, separate MySQL/PG volumes, synthetic account/course and child services. It inherits no provider credentials, uses offline cached public embeddings, disabled Java real providers, an Agent socket guard and an authored-only factory. The same real Java gateway and Evidence authority serve Chromium through the actual Vue course workspace. The Java JAR is reused only after confirming unchanged backend source/resources; its digest is recorded. Dependencies are pinned by the unchanged lockfiles. Resource limits apply only to this test stack. Cleanup removes its containers/network but retains test volumes; raw synthetic turns/usage/reservations are exported before cleanup.

Example from this checkout, with a new output path and already prepared public embedding cache:

```bash
python3 scripts/dev/run_check.py --name phase1d-cross-UNIQUE --cwd . --timeout 850 -- \
  python3 eval/phase1d-lightweight/integration.py \
  --output-dir /absolute/task-owned/evidence/UNIQUE \
  --instance phase1d-unique \
  --embedding-cache-source /absolute/public/offline-model-cache
```

Do not run against an existing project identity, occupied ports or business database. For this host's disk/log constraint the unmodified supervisor was copied to a new task-owned RAM root; all records were then copied to durable `.data/phase1d/evidence/`. See the report for actual executions and failures, not this example. Browser uses installed `/opt/google/chrome/chrome`; only loopback URLs are allowed. Auth tokens are passed in memory over stdin and never saved in browser state files or reports.

The authored answers include both valid mechanisms and deliberate negatives. Their assertions establish neither independent semantic review nor new real-model quality. A separately authorized real adapter/admission and independent quality review remain necessary before any paid trial.
