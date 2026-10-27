# P7 evaluation hardening (offline verification only)

This is a new, unshipped evaluator outside the frozen `lecturelens_agent` package. Generation uses `deepseek-flash`, thinking disabled; source review uses `deepseek-v4-pro` at `https://api.deepseek.com`. The channel admits exactly those models in their respective roles, rejects mixed generation/review tools, and records each model in both ledger events. No real provider requests have been made for this hardening round. Mock results verify execution and accounting, not model quality. Product flashcards remain Mock only.

The learner supplies a goal; the model selects search, observes lecture-scoped evidence, then chooses more search, card creation, or `stop_cards`. The frozen graph stores cards or the stop outcome. Generation has at most three requests per task. Every completed task receives two independent review requests, including empty-card stops. Review prompts contain only cards and cited source text; they contain no task goal, expected label, generator history, or other review. The second pass permutes card order deterministically (seed 20261028), with indices mapped back before scoring. Both passes must say `supported` for support credit; a disagreement, missing verdict, or `unclear` gets none. Matching unsupported verdicts remain unsupported. Failed trials and proposals are retained; no repair calls or retries are made.

The [32 tasks](tasks.json) copy the previous round's 24 unchanged and add eight confusable negatives, one per lecture. Their neighboring concepts were fixed before the snapshot absence checks. Each records literal, case-insensitive `evidence_absence_check` terms; `rg --ignore-case --fixed-strings` on that lecture's concatenated snapshot evidence returned zero matches for every term. Tests repeat the check. Lexical absence is an audit aid, not proof of semantic absence. Expected negative behavior is `stop_cards` with no cards. The two neutron-star off-topic tasks remain. This reuses public, known MIT courses and the immutable [snapshot](../p7-real/snapshot.json); it does not establish fresh held-out or unseen-course generalization. Source attribution, PDF hashes, page locations, and license remain in that snapshot. Compatibility page slots are not media timestamps.

## Frozen gates

[frozen.json](frozen.json) hashes tasks, thresholds, evaluator code, audit scripts, compose, and the prior manifest before any live run. Preflight also verifies the complete prior P7 freeze and development candidate. Changing any frozen input refuses dispatch; changed candidates require a new freeze and independent future holdout data for an acceptance claim. Previous assets and failed results are never rewritten.

| Gate | Pass line |
| --- | --- |
| citation_valid_rate | 1.0; any nonexistent/wrong-lecture ID stops the round, FAIL |
| source_supported_rate | >= 0.85; all generated cards are the denominator |
| offtopic_correct_stop_rate | 1.0 (2 tasks) |
| confusable_correct_stop_rate | >= 7/8 (floor(0.875 * n) correct if n increases) |
| false_stop_rate | <= 0.10 of 22 positive tasks |
| review_self_agreement | >= 0.90; identical verdicts / all generated cards |
| near_duplicate_agreement | >= 0.90 when pair n >= 3; otherwise `insufficient_n` |
| protocol_failure_rate | <= 0.05; tasks with generation or review protocol failure / 32 |
| p95_generation_latency_s | <= 20; nearest rank, whole generation path |
| max_calls / max_usd | 220 / $0.60, including both review passes |

Near-duplicate pairs span the whole run, require identical cited evidence-ID sets, and have either identical normalized back text or token-Jaccard >= 0.8 over front+back. Agreement compares final three-way verdicts; the summary reports pair n even when insufficient. PASS requires all enforced gates and all 32 tasks completed. Non-fabrication quality/protocol misses yield PARTIAL. Fabrication or channel/ledger errors yield FAIL. Protocol failures count once per affected task, including reviewer schema errors; no-review/missing-review cards cannot inflate support or self-agreement.

## Channel and isolated PostgreSQL

Only project `lecturelens-p7-hardening-20261027`, port `127.0.0.1:25721`, is used. Start the existing container without removing its volume:

```bash
cd /home/dev/projects/lecturelens-p7-eval-hardening
COMPOSE_DISABLE_ENV_FILE=1 docker compose -p lecturelens-p7-hardening-20261027 -f eval/p7-hardening/compose.yaml start postgres
```

The existing databases are `lecturelens_agent_acceptance` (evaluation) and `lecturelens_agent_test` (full tests). Ledger tests create and clean individual schemas in the acceptance database, with no `public` fallback that could reuse a retained standalone run's artifacts. Do not connect this evaluator to business PostgreSQL/MySQL databases. To provision this project on a fresh machine, use the same compose file with `up -d`, then create `lecturelens_agent_test` as `p7`; do not delete an existing volume.

The inherited channel preserves reserve-before-send with fsync'd append-only JSONL mirrored to synchronous PG, per-event consistency checks, persistent caps, single-use run IDs, unknown-outcome blocking, no retries, credential redaction, bounded bodies, and no redirects. Divergence blocks dispatch without automatic repair/refund. Failed requests consume full reservation; over-reservation usage is recorded at actual cost and blocks the round. DeepSeek parallel calls preserve e1e7af2 behavior: validate tool names/JSON, execute only the first, and count dropped calls.

Conservative prices ignore cache discounts. Integer nano-USD/token rates are (input, output) `deepseek-flash=(300,1200)` and `deepseek-v4-pro=(1740,3960)`, equivalent to $0.30/$1.20 and $1.74/$3.96 per million tokens. Input token reservation uses the complete request body's UTF-8 byte length; output uses `max_tokens <= 1200`. At 65536 bytes, maximum per-request reservations are $0.0211008 and $0.11878464 respectively. Reservations can exhaust $0.60 well before 220 calls; completing the round within this budget is not guaranteed. The normal Mock path makes 128 fake requests (64 generation, 64 review), creates 22 cards, and charges synthetic usage $0.04608. Zero real cost is incurred by Mock.

## Offline checks and Mock run

The suite wrapper strips provider credentials and the live switch and installs an inherited socket fence allowing only this PG port and ephemeral loopback test servers. Existing channel tests exercise synthetic live-branch requests through injected transports; these never reach a provider. No shell live switch is set during verification.

```bash
AGENT_TEST_DATABASE_URL='postgresql://p7:p7-local-only@127.0.0.1:25721/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25721 --network-records .data/p7-hardening/checks/network-confirmation \
  -- -q --junitxml=../.data/p7-hardening/checks/confirmation.xml
uv run --project agent-service --offline ruff check agent-service eval/p7-hardening

env -u AGENT_LLM_API_KEY -u LECTURELENS_REAL_EVAL \
uv run --project agent-service --offline python eval/p7-hardening/run.py \
  --dsn 'postgresql://p7:p7-local-only@127.0.0.1:25721/lecturelens_agent_acceptance' \
  --ledger .data/p7-hardening/mock-ledger-20261027.jsonl \
  --max-calls 220 --max-usd 0.60 --run-id p7-hardening-mock-20261027
```

Use new run IDs, ledger filenames and network-record directories for subsequent trials. Artifacts live under `.data/p7-hardening/<run-id>/`: `generations.jsonl`, `reviews.jsonl` (both passes, order, usage, errors, final verdicts), `summary.json`, `sample.md`, and `human-verdicts.template.json`. Keep private records outside Git.

Offline verification on 2026-10-27: the commands above produced **985 passed, zero skipped** (45 new hardening tests; 53 historical evaluator tests included), with ruff passing. An earlier full run recorded 984 passed and one existing MCP `mismatched_text` test returning `MCP_SERVER_UNAVAILABLE` instead of `MCP_MALFORMED_RESPONSE`; that test passed alone and in the complete confirmation run. Both records are retained under `.data/p7-hardening/checks/`. Two dependency deprecation warnings remain. The standalone Mock run completed 32/32 tasks with 22 cards, 64 flash + 64 pro fake requests, synthetic ledger charges $0.04608, support/self-agreement/duplicate agreement 1.0 (9 duplicate pairs), both negative stop rates 1.0, false-stop/protocol rates 0, and generation p95 1.4651 seconds. Its mirrored ledger check found no pending calls or block. These are mechanism results only; real requests and real cost remain zero.

## Human audit

```bash
uv run --project agent-service --offline python eval/p7-hardening/sample.py .data/p7-hardening/<run-id>
uv run --project agent-service --offline python eval/p7-hardening/agreement.py \
  .data/p7-hardening/<run-id> /path/to/filled-human-verdicts.json
```

`sample.py` uniformly selects ten cards (or all if fewer) with seed 20261028 and exports front/back, exact cited text/page, a stable `task_id:index` key, and a blank human verdict column. Reviewer labels are hidden. Fill a copy of the JSON template with `{card_key: "supported"|"unsupported"|"unclear"}`. `agreement.py` rejects blank/unknown keys, recomputes the conservative reviewer verdict from both stored passes, and reports exact three-way human agreement and n. Human review does not rewrite the model trial or gate results. Different-model review remains model opinion; correlated errors and small audit samples remain limitations.

## Reviewer-only live command — not executed here

Both `--live` and the process switch are required. A reviewer prepares `eval.env` with `LECTURELENS_REAL_EVAL=1` and `secrets.env` with `AGENT_LLM_API_KEY`; the program reads only process variables. The following sourcing is exclusively for that later, authorized live run, with shell tracing disabled:

```bash
cd /home/dev/projects/lecturelens-p7-eval-hardening
(
  set +x
  set -a
  . /home/dev/lecturelens-eval/deepseek-20261027/eval.env
  . /home/dev/lecturelens-eval/deepseek-20261027/secrets.env
  set +a
  uv run --project agent-service --offline python eval/p7-hardening/run.py \
    --live \
    --dsn 'postgresql://p7:p7-local-only@127.0.0.1:25721/lecturelens_agent_acceptance' \
    --ledger /home/dev/lecturelens-eval/deepseek-20261027/ledger-p7-hardening-20261027.jsonl \
    --max-calls 220 --max-usd 0.60 --run-id p7-hardening-real-20261027
)
```

`--check-ledger` with the same policy/run/ledger parameters checks both stores without dispatch or key lookup. Do not restart a used run ID. After review, stop only this project's PostgreSQL with `docker compose -p lecturelens-p7-hardening-20261027 -f eval/p7-hardening/compose.yaml stop postgres`; retain its volume. No deployment, release, or online configuration change is implied.
