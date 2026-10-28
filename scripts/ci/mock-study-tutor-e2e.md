# Local cross-service mock smoke

`mock-study-tutor-e2e.py` starts the actual packaged Java application, the opt-in
Tutor/Study Python application and fresh PostgreSQL plus demo infrastructure. It
uses synthetic accounts and a generated video. Deterministic provider decisions
exercise tool observations and saved outcomes; this is execution/protocol evidence,
not real-model teaching quality. Product budgets, locks and worker counts are unchanged.

Prerequisites: Java 21, Maven wrapper dependencies, Docker Compose >=2.24.4
(`!override` for loopback-only port mappings), Python 3.12/3.13, `uv`, FFmpeg,
and locally cached Python dependencies. Run from the repository root. No existing
`.env` or credentials files are read. Build/dependency setup is offline and the
script builds the jar if absent. Allow about 15 minutes per invocation (12-minute
execution deadline plus cleanup); logs remain after both success and failure.

Prepare public, pinned local embedding weights once, separately from the smoke.
This downloads model assets, without a hosted inference request or product spend:

```bash
(cd agent-service && uv sync --offline --frozen)
env -u HF_TOKEN -u HUGGING_FACE_HUB_TOKEN HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
  agent-service/.venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download(
    'qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q',
    revision='faf4aa4225822f3bc6376869cb1164e8e3feedd0',
    cache_dir='/tmp/lecturelens-public-embedding-models',
    allow_patterns=['*.json', 'model_optimized.onnx'], token=False,
)
PY
python3 scripts/ci/mock-study-tutor-e2e.py \
  --output-dir /tmp/lecturelens-smoke-1 \
  --embedding-cache-source /tmp/lecturelens-public-embedding-models
```

Run again with a new output directory for stability. The cache is copied into each
run's private directory and loaded offline. No external Agent socket connections
are allowed by the interpreter audit hook. Uvicorn launches the test-only
`scripts.ci.tutor_hold_app:create_app` factory, which calls the real application
factory and wraps its default mock Tutor provider in process. Product source,
retrieval and authority remain unchanged. The Agent working directory is
`agent-service`; PYTHONPATH includes the network guard and repository root. Java real-provider switches
are false and no caller provider credentials/proxies/JVM options are inherited.
This does not provide OS-level Java packet attribution.

The harness reserves project names `lecturelens-demo-pr49smoke` and
`lecturelens-agent-pr49smoke`. It refuses preexisting labeled containers, volumes
or networks, checks all requested ports, selects and records free alternatives
on conflicts, and rechecks immediately before binding. All published ports and
application listeners bind `127.0.0.1`. Only its own children and freshly owned
projects/volumes are stopped/removed. Secrets are generated in memory and passed
in process environments; `public.env` contains no generated secrets. Child output
is redacted before reaching logs; HTTP bodies and JWTs are not logged.

Stage results and durations are saved to `result.json`. The smoke requires:

- Tutor create/list, a completed answer with current source citation or the exact
  documented abstention, immediate queued-cancel with submission status exactly
  `queued`, reaching `cancelled` with an empty/null answer, empty citations and
  `model_calls == 0` / `tool_calls == 0` in both the API and PostgreSQL; running-cancel
  with a held decision and stable empty publication; a normal same-Session follow-up;
  then `SIGKILL`/restart with identical persisted history and a new completed question.
- Flashcards create Session, generate and poll Run to `succeeded`, due/read/review
  with Good, version increment, changed schedule and removal from the due queue.
- A second authenticated account receives exactly HTTP 404 on all five Tutor
  routes and Study DUE/READ/GENERATE. Actual codes are recorded before assertion;
  other errors never count as permission denial.
- MySQL lacks Agent state table prefixes; PostgreSQL has expected owner/course
  Sessions, turns, Run, deck, cards and review through their ownership joins.
  These are **heuristic + not proven** process-level write attribution.
- Mock-only Run state, no configured model connections, active Agent network
  guard and zero attempted non-loopback Agent connections.

A failed assertion is retained as FAIL; dependent stages remain NOT_RUN. Do not
change product behavior or assertions to bypass a failure. Vue/Playwright is
FOLLOW_UP. Real-provider task quality is NOT_RUN.

`Tutor-running-cancel` arms the test-only factory’s `TUTOR_MOCK_TEST_HOLD_DIR`
protocol in the private run directory. The Agent receives the directory at startup;
only an `arm` file activates it. Mock `decide` writes `entered` and polls for
`release` every 50ms for at most 10 seconds, then resumes its normal decision on timeout.
The factory rejects startup outside `AGENT_LLM_MODE=mock`, before workers start.
The bounded wait also bounds shutdown; no worker threading or cancellation logic changes.

The harness requires `entered`, API/PG `running`, a persisted deadline and a
`reserved` checkpoint before CANCEL. It disarms and releases the decision after
CANCEL, checks API/PG `cancelled` with no answer/citations immediately and again
after three seconds, then completes a new question in the same Session.
`model_calls == 1` is the durable reservation before entering `decide`;
`tool_calls == 0` proves cancellation fenced the returned decision before tool
execution. These counters are required in both API and PG. Queued-cancel still
requires both counters to be zero. Markers and observations remain in the run
output. Any late publication fails the stage and is a product bug; the harness
does not repair cancellation behavior.

To verify the original script independently, the helper mode creates only fresh
demo infrastructure and launches the original, unchanged `mock-e2e.py`; no Agent
or Agent PostgreSQL is started:

```bash
python3 scripts/ci/mock-study-tutor-e2e.py \
  --output-dir /tmp/lecturelens-legacy-alone --legacy-only
python3 -m unittest scripts.ci.test_mock_study_tutor_e2e -v
agent-service/.venv/bin/python -m unittest scripts.ci.test_tutor_hold_app -v
```
