# P10 choice review mechanism acceptance

P10 reads existing P9 judgments across Sessions within owner/course/revision. It creates no model task or learner profile. The independent development identity is `p10-choice-review-442bb2af75c77ed1` (63 modules, manifest SHA-256 `442bb2af75c77ed1f1a0d4b858dce9b43751b5eb4e9d9e7ff5835a5609c870ab`). Historical P9/P7/FROZEN manifests and Tutor's 18 frozen inputs remain unchanged. The `p10-prior-source.tar.gz` fixture contains P9 contracts/store bytes from main `e05bf72eda49484142dd1fc2b5656a1303b9d8dc`; tests reconstruct historical candidates without Git access.

Run long checks through `scripts/dev/run_check.py`, using distinct output names and retaining failures. Node is `/opt/node/bin`. For example, from this worktree:

```bash
python3 scripts/dev/run_check.py --name python-full --timeout 1500 --output .data/p10-acceptance/checks -- agent-service/.venv/bin/python eval/p10-review/run_tests.py --output .data/p10-acceptance/python-full
python3 scripts/dev/run_check.py --name frontend --timeout 600 --output .data/p10-acceptance/checks -- bash -c 'export PATH=/opt/node/bin:$PATH && cd frontend && npm run test:unit && npm run type-check && npm run build'
python3 scripts/dev/run_check.py --name java --timeout 600 --output .data/p10-acceptance/checks -- bash -c 'cd backend && bash mvnw -o -B -Dtest=StudyChoiceGatewayTest,StudyControllerTest,StudyAuthorityTest,TutorControllerTest,TutorTransportTest test package'
python3 scripts/dev/run_check.py --name browser --timeout 1200 --output .data/p10-acceptance/checks -- python3 eval/p10-review/browser_acceptance.py --output .data/p10-acceptance/browser
```

`run_tests.py` starts its own loopback pgvector/PG17 container using the CI-pinned image, Python's environment-only random password, `lecturelens_agent_test` with vector, and `lecturelens_agent_acceptance` on the same new instance. Default commands are CI's Ruff checks and full `uv run pytest -q`; `--tests ...` explicitly selects a subset and must not be reported as full. `--mutations` runs the negative controls in that same isolated environment. Cleanup removes only the exact new container and its tmpfs databases. Skipped DB cases are not a complete pass.

`browser_acceptance.py` requires clean committed source and previously built Java/Vue. It uses dedicated P10 Compose projects, synthetic preview account/material, actual product Mock generation/grading, and the existing P9 offline embedding adapter. It runs real Vue -> Java -> Python -> independent MySQL/PostgreSQL, loopback-only; no HTTP/grade fixtures. It records SHA, source cleanliness, screenshots, HTTP observations and redacted logs, then tears down owned resources. The Agent network guard denies non-loopback access; Java's real-provider switches are disabled. No paid model calls.

The browser checks wrong submission, cross-Session persistence, refresh, original-question restoration, canonical Evidence time navigation, removal after a newer correct version, empty state and unchanged open-answer/feedback, continuation, Tutor and flashcard flows. Existing P9 before-grade privacy and blank rejection checks remain included.

Local results and the English PR draft belong under this worktree's ignored `.data/p10-acceptance/` with exact SHA attribution. Real-provider quality, stress/load tests, mobile-specific acceptance, deployment and new GitHub CI are NOT_RUN unless separately recorded. Stop before push or PR creation/update.
