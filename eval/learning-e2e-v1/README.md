# Mock learning-flow acceptance

This is a local functional acceptance, not a real-provider quality evaluation.
It reuses the P10 full-stack harness and P9 offline hash embedding adapter, with
fresh Compose project names, accounts, synthetic media and databases. The browser
extends P10's unchanged choice/review scenarios with actual course entry and media
decoding, multi-turn/Socratic Tutor, conversation recovery, flashcard recovery and
versioned feedback correction. Two deliberate lost-response faults execute the
real server request, discard its response, then exercise the UI's idempotent retry.
No successful API responses are fabricated. Original P10 assets remain unchanged.

Build the current worktree's Java jar and Vue bundle before running; see
[P10 prerequisites](../p10-review/README.md). Use a clean local commit, cached
dependencies, Java 21, Node `/opt/node/bin` and sandboxed Chrome. No existing
environment/credential files are passed to services. The preview enables the
existing optional feedback feature only in its own environment; product defaults
and historical Agent identities remain unchanged.

```bash
export PATH=/opt/node/bin:$PATH
python3 scripts/dev/run_check.py --name learning-browser --timeout 1200 \
  --output .data/learning-e2e-NEW/checks -- \
  python3 eval/learning-e2e-v1/browser_acceptance.py \
    --output .data/learning-e2e-NEW/browser
```

The harness refuses existing resources under its reserved project names
`lecturelens-demo-learninge2e` / `lecturelens-agent-learninge2e`, selects free
loopback ports, generates secrets in memory and redacts child logs. Python denies
non-loopback sockets; Java provider switches are disabled; browser external
requests are blocked and Chrome's sandbox stays enabled. These controls are not
OS-level attribution of all Java packets. Only newly owned services and volumes
are removed. Before teardown, synthetic PostgreSQL learning rows are exported to
`synthetic-state.json`; screenshots and browser HTTP observations remain alongside
stack logs, failures and cleanup results. Keep these raw outputs ignored by Git.

Desktop acceptance does not cover mobile, Safari, real-provider content quality,
ASR accuracy, long-term retention, load, production or deployment. Mock outcomes
must not upgrade existing real-model quality conclusions.
