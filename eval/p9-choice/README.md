# P9 local mechanism acceptance

This is a new Mock-only choice-practice candidate. It does not inherit a frozen AU/P7/Tutor identity or real-model quality result. Historical manifests and the Tutor/flashcard product modules remain unchanged. The shared practice contracts, persistence and dispatcher legitimately change for P9; the P7 identity verifier must reject this runtime rather than repin its manifest.

Prerequisites are the same as [`scripts/ci/mock-study-tutor-e2e.md`](../../scripts/ci/mock-study-tutor-e2e.md): cached Docker images/Maven/Python dependencies, Java 21, `uv`, FFmpeg, Chrome and Node at `/opt/node/bin`. No production `.env` files are read by the harness. Use an isolated worktree. All evidence below is generated under this worktree's ignored `.data/p9-acceptance/` directory, including failed trials.

```bash
export PATH=/opt/node/bin:$PATH
python3 scripts/dev/run_check.py --name frontend --timeout 360 --output .data/p9-acceptance/final/checks -- bash -c 'cd frontend && npm run test:unit && npm run type-check && npm run build'
python3 scripts/dev/run_check.py --name java --timeout 600 --output .data/p9-acceptance/final/checks -- bash -c 'cd backend && bash mvnw -o -B -Dtest=StudyChoiceGatewayTest,StudyControllerTest,StudyAuthorityTest,TutorControllerTest,TutorTransportTest test package'
python3 scripts/dev/run_check.py --name python-db --timeout 1000 --output .data/p9-acceptance/final/checks -- python3 eval/p9-choice/run_tests.py --output .data/p9-acceptance/final/python agent-service/tests/test_study_choices.py agent-service/tests/test_study.py agent-service/tests/test_study_attempts.py agent-service/tests/test_study_feedback.py agent-service/tests/test_study_resilience.py agent-service/tests/test_study_approval.py agent-service/tests/test_flashcards.py agent-service/tests/test_scheduling.py agent-service/tests/test_learning_scope.py agent-service/tests/test_learning_scope_transport.py agent-service/tests/test_study_trace.py
python3 scripts/dev/run_check.py --name mutations --timeout 600 --output .data/p9-acceptance/final/checks -- python3 eval/p9-choice/run_tests.py --mutations --output .data/p9-acceptance/final/mutations
python3 scripts/dev/run_check.py --name browser --timeout 900 --output .data/p9-acceptance/final/checks -- python3 eval/p9-choice/browser_acceptance.py --output .data/p9-acceptance/final/browser
```

`run_tests.py` creates a new disposable loopback PostgreSQL with a random password passed only in child environments. The DB name is `lecturelens_agent_test`; it is separate from the browser's application database. Its supervisor records actual exit codes and pytest output. A skip is not a database pass. Cleanup removes only its exact newly created container.

The browser harness reuses repository smoke infrastructure with dedicated P9 project identities, fresh volumes/accounts/material and loopback bindings. It launches the actual packaged Java application and the unchanged opt-in Tutor ASGI factory with the real P9 Study runtime. The only injected adapter is deterministic offline embedding; generation/grading use product code. The Agent has a non-loopback socket guard. Java real-provider switches are disabled; this is configuration evidence, not OS-level Java egress attribution. No HTTP responses or grade rows are fabricated.

The preview explicitly sets `AGENT_LLM_MODE=mock` and `STUDY_FEEDBACK_ENABLED=true` to exercise the existing optional open-answer feedback/note path. The product default remains off. Passwords and signing secrets are generated in memory, passed through environments and redacted from child logs. Chrome keeps its sandbox and uses a short private temporary path; that temporary profile is removed after teardown.

Browser assertions cover generation, blank selection rejection, READ/ANSWERS before-grade privacy, wrong then correct selections, exact source/time navigation, version history, reload persistence, open-answer non-grading, feedback/check-note completion, P5 continuation, Tutor/flashcard coexistence and 1280px reentry. The report records `source_dirty`: only a clean final-HEAD run is final acceptance. Development runs are retained separately.

After all source changes and local commit, rerun the checks and browser on that exact HEAD. `.data/p9-acceptance/final/REPORT.md`, `identity.json`, `sha256.json`, `PR_BODY.md` and the browser result/stack records form the local delivery bundle. These generated files are not published to GitHub.

NOT_RUN unless separately authorized and recorded: real-provider task quality, Tutor evaluation, stress/load testing, mobile-specific acceptance, production deployment and new GitHub CI. This workflow stops before push or PR creation/update.
