# P8 multi-turn Tutor evaluation channel

Offline mechanism implementation only; **zero real provider calls** in this task. Mock PASS is not teaching quality. This directory freezes 24 dialogues/80 learner turns over the same eight public snapshots as [P7](../p7-real/README.md). Neither frozen P7 assets nor AU/CostPolicy behavior changes. All local outputs belong in ignored `.data/p8-tutor/<run_id>/`.

The first authorized live trial, `p8-real-review-20261027`, remains **FAIL** after **2 real calls / $0.0039189**, with `REAL_EVAL_CITATION_FABRICATED`. Its Flash answer used `Adj[u]`; the old bracket parser misclassified `u` as an evidence id. All 11 actual declared/inline ID references were authoritative. This was an evaluator/contract false positive; the failed run and its original ledger are retained as evidence, without rescoring it as a pass. See [the fix report](REPORT.md#offline-fix-round-1).

Candidate **`p8-tutor-20261027-v4`** preserves the shared citation grammar and authority checks. Observed citation-format mistakes (including missing inline references or duplicate declarations) and missing evaluation after a Socratic prompt produce error observations, consume a tool slot and allow a corrected finish within the existing four-model/four-tool turn budget. Unobserved/fabricated IDs and authority failures remain fatal. Two authoritative searches are allowed per turn; after that only finish is offered. Exact abstention and guiding-question requirements remain enforced. Finish size limits remain four evidence IDs, 500 evaluation characters and 1,600 text characters. Exactly one size-only repair observation (`TUTOR_FINISH_LIMIT_EXCEEDED`) is allowed per turn; it consumes a tool slot and survives restart through the committed journal. A second size violation is a failed turn/protocol miss. No proposal is truncated. The eval adapter defers only these three upper bounds to the runtime; all other strict schema constraints and every declared/inline authority check, including dropped parallel calls, remain enforced. Dialogues and thresholds are byte-identical to `970bd00`; all pinned inputs were rehashed, including the isolated compose file.

The separately executed r2 trial remains **PARTIAL**. Its citation, search-budget and missing-evaluation failures motivated this offline protocol change; they are not rescored as successes. The separately authorized focused trial `p8-protocol-focus-20261027` remains **PARTIAL**, with four Finish-size protocol failures reported by the operator. Its artifacts remain unchanged. This offline size-repair round does not rescore those failures. See [schema verification](REPORT.md#offline-finish-schema-repair-v4). The proposed full live run below is **not executed** here.

## Scripts and negative evidence

Each lecture has dialogues `-1` (definition/explanation, 3 turns), `-2` (Socratic prompts and a learner reply, 3 turns), and `-3` (comparison, 3 supported turns and one related absent-topic follow-up). Every dialogue contains “Why is that?” and another elliptical/reply follow-up. Expected prior topics are passed only to the independent reviewer. They are never supplied to the Tutor. The scripts have 56 context-dependent follow-ups, eight insufficient-evidence turns and 24 Socratic turns in eight dialogues.

| Lecture | Topics across dialogues 1 / 2 / 3 | Absent extension in dialogue 3 | Zero-hit grep term |
| --- | --- | --- | --- |
| algorithms-l1 | adjacency lists / BFS levels / directed vs undirected graphs | distributed graph processing | `Pregel` |
| algorithms-l2 | back edges / topological sorting / edge classification | another SCC algorithm | `Gabow` |
| algorithms-l3 | relaxation / Dijkstra conditions / DAG shortest paths | road-network preprocessing | `contraction hierarchies` |
| probability-l1 | axioms / sample spaces / union bound | Bayesian posterior | `Dirichlet` |
| probability-l2 | conditioning / total probability / Bayes | Bayesian estimation prior | `Jeffreys` |
| probability-l3 | independence / conditional independence / pairwise vs mutual | exchangeable sequences | `de Finetti` |
| quantum-l1 | superposition / measurement / classical vs quantum | open-system dynamics | `Lindblad` |
| quantum-l2 | interference / polarization / single photons | two-photon coincidence | `Hong` |

These terms have zero case-insensitive literal hits in the corresponding lecture's complete evidence text. Absence is reverified in `verify_inputs()` and `test_frozen_scripts_absence_and_threshold_hashes`. To independently grep a lecture, extract its text to a local file and run, for example:

```bash
python3 - <<'PY' > .data/p8-tutor/algorithms-l1-source.txt
import json
s = json.load(open('eval/p7-real/snapshot.json'))
print('\n'.join(e['text'] for e in s['lectures']['algorithms-l1']['evidence']))
PY
rg -ni -F 'Pregel' .data/p8-tutor/algorithms-l1-source.txt
# Expected: zero lines, exit code 1. Use the table's lecture and term for other rows.
```

Absence of a distinctive name is a reproducible negative-data check, not a proof that every related question is unanswerable. The scripts deliberately request the named absent method/phenomenon; no substantive extension is allowed on those turns. All failed proposals/reviews remain failures.

Sources are `eval/retrieval-v2/corpus.json` with P7's read-only `snapshot.json` projection: MIT OCW, CC BY-NC-SA 4.0, source URLs, page locators and content hashes retained. The snapshot's `page*1000` slots are **not video timestamps**. Runtime citations are enriched with original page/source text for human audit. Public known-course scripts are not an independent unseen-course holdout.

## Channel and frozen gates

The eval adapter drives the production Tutor store/runtime with a read-only snapshot authority. The model chooses contextual search, observes evidence and chooses another search or a finish outcome. Tutor routes only to **deepseek-flash**, reviewer routes only to **deepseek-v4-pro**. Tutor tools cannot be sent to the reviewer model, or review tools to Flash; the ledger independently checks model/tool routing. Reviewer context contains the conversation, expected prior topic, mode, answer/evaluation and cited source text, without hidden reasoning or negative labels. Review is on by default; `--no-review` cannot establish PASS quality. Every returned tool proposal is inspected, including ignored parallel calls.

`thresholds.json` and implementation/source inputs are SHA-256 recorded in `frozen.json`; preflight refuses changed bytes before any send. The frozen manifest digest is recorded in both run policy and summary. Any future changes require a new candidate, with earlier failures retained.

| Metric | Frozen threshold |
| --- | --- |
| citation_verifiable_rate | 1.0; any fabricated ID stops the entire round with FAIL |
| no_evidence_abstain_rate | 1.0; explicit outcome, no citations/claims, independent clean-abstention judgment |
| answer_supported_rate | ≥0.85; independent reviewer on answered turns |
| context_retention_rate | ≥0.90; reviewer resolves scripted prior topic on follow-ups |
| socratic_compliance_rate | ≥0.75; guiding question/hint, no full-answer dump |
| protocol_failure_rate | ≤0.05 per learner turn |
| p95_turn_latency_s | ≤20; nearest rank, Tutor execution only |
| max_calls / max_usd | 400 / $0.70, reviewer included |

All 24 dialogues/80 turns and all gates are required for PASS. Nonfatal quality/protocol misses are PARTIAL. Fabricated citations, channel/ledger errors or unknown outcomes are FAIL. Missing/failed reviews count as unsupported, not successful. Citations in malformed proposals are inspected before schema validation so malformed output cannot hide invented IDs. An insufficient-evidence candidate containing substantive text is rejected by the runtime, never rewritten into a passing answer.

The P8 channel derives from P7's reserve-before-send pattern with separate `p8_tutor_real_run/p8_tutor_real_event` PG tables. It preserves an append-only fsynced JSONL mirror, exclusive locking, durable PG commit and exact record comparison before dispatch. No transport/schema retry and no automatic ledger repair. Runtime tool-error observations permit another model-selected attempt within the original persistent turn budget; each decision is separately accounted. Unknown/failed outcomes consume the full reservation and cannot be replayed. Actual usage exceeding reservation blocks the run. There is no product adapter importing this channel.

Conservative fixed ceilings per million tokens: Flash **$0.30 input / $1.20 output**; Pro **$1.74 input / $3.96 output**, cache discounts ignored. Input reserves the complete wire-body byte count as a token upper bound; output ≤1,200 tokens; body ≤65,536 bytes; response ≤128 KiB; timeout ≤20 seconds. Largest reservations are $0.0211008 Flash / $0.11878464 Pro. These conservative reservations can exhaust $0.70 before 400 requests; completion within the cap is not guaranteed. Normal mock flow has 160 Tutor requests + 80 review requests = 240 fake requests.

## Own isolated database and offline checks

Only compose project `lecturelens-p8-tutor-protocol-20261027`, PostgreSQL `127.0.0.1:25741`:

```bash
COMPOSE_DISABLE_ENV_FILE=1 docker compose -p lecturelens-p8-tutor-protocol-20261027 \
  -f eval/p8-tutor/compose.yaml up -d
COMPOSE_DISABLE_ENV_FILE=1 docker compose -p lecturelens-p8-tutor-protocol-20261027 \
  -f eval/p8-tutor/compose.yaml exec -T postgres \
  psql -U p8 -d lecturelens_agent_acceptance -c 'CREATE DATABASE lecturelens_agent_test'
```

CREATE DATABASE is first-start only. Tests use `lecturelens_agent_test`; isolated ledger tests use temporary schemas in `lecturelens_agent_acceptance` on the same port. No MySQL tables or other compose projects are used. Guarded broad suite (use a fresh network-records directory for each invocation). Seven legacy P7 fake-transport security cases set the live opt-in internally; exclude them to keep the final run free of that switch. All Tutor/real-eval Tutor cases and database fixtures run normally:

```bash
AGENT_TEST_DATABASE_URL='postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25741 --network-records .data/p8-tutor/checks/schema-full-safe-network \
  -- -q \
  -k 'not (test_live_requires_both_switches or test_live_schema_failure_never_enters_chatprovider_repair or test_key_never_in_exception_logs_or_ledgers or test_parallel_tool_calls_execute_first_only_without_extra_request or test_parallel_tool_calls_with_unknown_tool_fail_closed)' \
  --junitxml=../.data/p8-tutor/checks/schema-full-safe.xml
```

Standalone default mock run; never use the external ledger path for mocks:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/schema-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/schema-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-schema-mock-20261027
python3 .data/p8-tutor/p8-schema-mock-20261027/sample.py -n 5
```

Outputs: `dialogues.jsonl`, `reviews.jsonl`, `summary.json`, and standalone `sample.py`. Sampling prints N seeded dialogues with turns, outcomes, inline citations and full cited source text. Summary explicitly labels fake runs `NOT_RUN_MOCK_MECHANICS_ONLY`. Fake transport does not read credentials; its fixed reviewer judgments and negative responses only verify mechanics.

## Exact live command for a later reviewer — DO NOT run in this task

The human operator must separately configure credentials and the required live opt-in in their shell. The application never loads private env files or sets the opt-in. This requested full-suite command is **documentation only**, with a fresh run ID/ledger and no dialogue filter:

```bash
cd /home/dev/projects/lecturelens-p8-tutor-protocol
uv run --project agent-service --offline python eval/p8-tutor/run.py \
  --live \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger /home/dev/lecturelens-eval/deepseek-20261027/ledger-p8-schema-full-20261027.jsonl \
  --max-usd 0.80 --max-calls 400 --run-id p8-schema-full-20261027
```

The requested `$0.80` argument exceeds the unchanged frozen `$0.70` policy ceiling; current preflight rejects it before dispatch. No cap was raised to accommodate this documentation-only command. An operator needs a separately resolved budget configuration before using it. The 24-dialogue/80-turn gates and all quality thresholds remain unchanged.

`--dialogue-ids` remains available for focused diagnostics. It accepts space-separated unique frozen IDs; empty, unknown or duplicate IDs fail before ledger/provider entry. Focused summaries record `scope=focused` and selected IDs and return **PARTIAL** at best, even with perfect metrics. These are public development scripts, not fresh holdout data.

`AGENT_LLM_API_KEY` is read only inside the live sender; raw errors, body text and keys never enter the accounting ledger/logs. Key echoes in parsed or raw provider responses are rejected. All requests use the fixed HTTPS DeepSeek route, no redirects, no environment proxy, no retries. To check consistency without sending/reading the key, add `--check-ledger` with the same run ID, caps and candidate. Each run ID is single-use; restart cannot reset its budget or resend an unknown call.

This round leaves the isolated PostgreSQL project running for reviewer inspection; the reviewer stops it and retains its volume.
