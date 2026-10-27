# P8 multi-turn Tutor evaluation channel

Experimental Tutor; **zero real provider calls in the v9 task**. Two historical v8 live trials passed the bounded known-course gates; v9 is offline only. Mock PASS is not teaching quality. This directory freezes 24 dialogues/80 learner turns over the same eight public snapshots as [P7](../p7-real/README.md). Neither frozen P7 assets nor AU/CostPolicy behavior changes. All local outputs belong in ignored `.data/p8-tutor/<run_id>/`.

The first authorized live trial, `p8-real-review-20261027`, remains **FAIL** after **2 real calls / $0.0039189**, with `REAL_EVAL_CITATION_FABRICATED`. Its Flash answer used `Adj[u]`; the old bracket parser misclassified `u` as an evidence id. All 11 actual declared/inline ID references were authoritative. This was an evaluator/contract false positive; the failed run and its original ledger are retained as evidence, without rescoring it as a pass. See [the fix report](REPORT.md#offline-fix-round-1).

Candidate **`p8-tutor-20261027-v9`** inherits controller-assembled citations. The model writes inline `[id]` citations in text/evaluation, with at most four distinct evidence IDs and no separate `evidence_ids` tool field. The controller extracts with the existing source-ID grammar, de-duplicates and preserves first appearance (text then evaluation); any legacy provider declaration is ignored, even if wrong or malformed. Every extracted candidate must be observed and authoritatively re-READ before repair; unknown/cross-lecture IDs still durably block the eval ledger, including rejected and dropped parallel proposals.

Excess distinct inline IDs and Finish size violations share the durable `TUTOR_FINISH_REPAIR_REQUIRED` chance. The observation includes `distinct_ids`, the full `evidence_ids` list, `keep_ids` (first four), `remove_ids` (the rest), legacy `excess_ids`, and all actual sizes/exact limits. A second violation fails with `TUTOR_FINISH_FORMAT_INVALID`. A separate one-shot `TUTOR_SOCRATIC_REPAIR_REQUIRED` and the legacy journal counters remain. Publication passes controller metadata and unchanged content through the original strict `Finish`: **4 IDs / 500 evaluation characters / 1,600 text characters**. No silent truncation, dropping or content/outcome rewriting is allowed. Zero-ID supported finishes and exact abstention retain their authority/contract checks.

Each repair atomically prepays the exact next finish-only request in the committed observation journal, under unchanged session/token caps. The ordinary four-model/four-tool limit has at most **one extra repair-only slot**, five total; two searches plus finish plus the two distinct repairs fit in five. Repair requests offer and accept only `finish_tutor_turn`. If capacity is unavailable, the turn fails with `TUTOR_REPAIR_BUDGET_UNAVAILABLE` before issuing a repair observation. An issued observation has its next runtime call/tool budget reserved. The persisted 20-second deadline, authorization, cancellation and fail-closed unknown-call recovery still apply. `TUTOR_EVALUATION_REQUIRED` keeps its previous ordinary-budget behavior.

The separately executed v4 and v5 full live trials remain **PARTIAL**. V5 `p8-repair-full-20261027` had 8/80 protocol failures, all repeated declaration/inline mismatches, and used **306 calls / $0.499732920**. This offline change does not establish real-model improvement. See [v6 verification, freeze and budget math](REPORT.md#offline-controller-assembled-citations-v6). Thresholds remain byte-identical to `970bd00`; v7 inherits v6’s approved union-bound should-abstain labeling with dialogue bytes unchanged. Caps remain **400 calls / $0.70**. Historical outputs are untouched; the live command below is documentation only.

The historical reviewer-retry v7 manifest SHA-256 is `a22f2b9e6af8d83c464e2200e14448de410d332a44b5f9eddb3b1ff40e433203`. The reviewer-retry update retains the candidate name and all 18 pinned paths, updating only the runner and mutation-harness digests. Reviewer protocol/request failures get at most **3 total attempts**, each accounted through the same run ledger and budget. Every review record includes `review_attempts`; an exhausted review records `REAL_EVAL_REVIEW_FAILED`, scores missing judgments false, and lets later turns/dialogues run. Blocked ledgers and hard eval errors still stop the suite. Tutor generation receives no new retries; citation rules are unchanged. That offline round left its live rerun **NOT_RUN**; the later retry-full result is described in the v8 section below. See [the reviewer-retry verification](REPORT.md#offline-reviewer-retry-and-suite-continuation-v7). Historical trials/reviews remain unchanged and are not rescored.

Reviewer-retry offline verification: **180 passed, 0 failed/errors/skipped; 13/13 mutants killed**, including removed retry and restored suite-fatal review failure (`review-retry`). All checks used fake transport and isolated PostgreSQL; real spend **$0**. These counts describe the earlier offline reviewer-retry round.

Earlier v7 context-rule verification (manifest `703a42e5a3b27f024e51ddf85eb526d79f1f208d5a84ad58df346e1bfb0e2c6b`): **172 targeted tests passed, 0 skips; 11/11 mutants killed** (`ctx-v7`). `p8-ctx-v7-mock-20261027`: **24 dialogues / 80 turns, PASS**; `p8-ctx-v7-focus-mock-20261027`: **12 / 41, PARTIAL by scope**, including `probability-l1-3`. Both have fixed context/abstention/citation/support/Socratic rates 1.0 and protocol failures 0. These are mock mechanics only, with **$0 real spend**.

## Per-turn union citable evidence (v9)

Citable evidence is the ordered union, de-duplicated by first appearance, of **all search observations in the current turn**. It starts empty each turn; citations in history or prior turns never enter it. The durable `selected` checkpoint retains the union across worker restarts. Both model prompt evidence and authoritative READ follow that order. Python issues READ in batches of at most eight IDs, preserving Java’s authority cap. At most two searches × eight rows yield **16 citable IDs**, without silent truncation; a published finish still permits only **4 IDs / 500 evaluation characters / 1600 text characters**. Repair keep/remove lists follow the proposed inline order and may include first-search IDs. Strict IDs outside the current-turn set still fail `TUTOR_CITATION_MISMATCH`; fabricated IDs still trigger the eval fatal path.

The v8 confirmation exposed two distinct cases: `quantum-l2-3` #2 cited `v2-quantum-l2-p05-e00`, observed in the first search but replaced by the second (allowed in v9); `quantum-l2-2` #2 cited `v2-quantum-l2-p04-e00`, seen only in a prior turn (still rejected). No historical trial is rescored.

| Historical v8 run | Verdict / spend | Supported | Context | Socratic | Protocol failures | Format repairs | Review retries |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `p8-finish-v8-full-20261027` | PASS / $0.574557 | .978 | 1.0 | 1.0 | 0.0 | 9 | 2 |
| `p8-finish-v8-confirm-20261027` | PASS / $0.519325 | 1.0 | .946 | .958 | .025 (2 citation mismatches) | 3 | 0 |

Union growth increases serialized request size and conservative reservations. Existing **64,000 turn tokens / 640,000 session tokens / 65,536 channel body bytes / 1,200 output tokens / 400 calls / $0.70** caps remain unchanged. Oversized requests stop before dispatch; capacity is never obtained by dropping citable IDs or raising caps. One format repair, context rules, reviewer limited retry, Socratic rules and exact abstention are unchanged. See [v9 verification and budget measurements](REPORT.md#offline-per-turn-union-citable-evidence-v9). **V9 live task quality: NOT_RUN.**

V9 final verification: **1171 full-suite tests passed, 0 failures/errors/skips/deselected; 231 targeted Tutor tests passed; 18/18 mutants killed** (requested `v9`, final-freeze `v9-final`). The requested `p8-ctx-v9-mock-20261027` and fresh final-freeze `p8-ctx-v9-mock-final-20261027` both **PASS**: 24 dialogues / 80 turns / 80 reviews / 240 fake requests, zero protocol failures. The earlier mock keeps its original manifest; the fresh run records final manifest **`370d61d64abf1921927ae7e5ba6e5cc6c1e887aeaa9f4ef792aef723e1117426`**. All 18 pins verify; Ruff lint/format pass. Threshold SHA-256 remains **`21d48ea5acd1fd63660fecd5ea03012aa5920ef048e0ff65430b68285be5b5da`**. All 43 guarded network-record groups report zero denied connections; real provider calls/spend **0 / $0**. Initial wording-test failure and the interrupted pre-batching rerun are retained in the report. **NOT_RUN:** v9 live quality, fresh holdout and unchanged Java/frontend checks.

## Actionable finish-format repair (v8)

The v7 retry-full trial `p8-ctx-v7-retry-full-20261027` had eight `TUTOR_FINISH_FORMAT_INVALID` turns (0.10 protocol failure), causing all nine context misses directly or by cascade. The earlier hypothesis that `[u]`/`[v]` were counted in this trial was wrong: the strict regex already excluded `[u]`, `[v]`, `[A]` and `[x_1]`. Strict distinct IDs in first → repaired finishes were **5→5, 6→5, 5→4 (1641 text chars), 6→5, 6→5, 5→4 (1762 text chars), 7→6, 6→5**. The model usually removed only one ID or left text over 1600 characters.

V8 puts the same instructions in the system prompt and finish tool description: prefer 2–3 IDs, at most four across both fields, text target ≤1200 (hard limit 1600), evaluation ≤500, observed IDs only, and parentheses for math. Repair feedback explicitly lists the first four `keep_ids` and all `remove_ids`; the model must delete every removed citation and its unsupported claims, re-attribute only when kept evidence supports the claim, and introduce no new IDs. Overlength fields receive actual character counts, exact maxima and rewrite targets. The model must resubmit. The 1200-character target is guidance; strict 4/500/1600 publication limits, authority checks, one format repair, context rules and reviewer retry are unchanged.

The candidate manifest SHA-256 is `4e0cce141a6c6393e894b86b843ef3965fabd0ec71c92cb21e3f7a5812b9baa2`. Threshold SHA-256 remains `21d48ea5acd1fd63660fecd5ea03012aa5920ef048e0ff65430b68285be5b5da`. Minimal ID/length fixtures replay all eight first finishes with fake repairs; they test format mechanics only. That offline round left real-model v8 evaluation **NOT_RUN**; the two later live results are recorded above. See [v8 verification](REPORT.md#offline-actionable-finish-format-repair-v8).

V8 offline verification: **223 targeted tests passed twice, 0 failures/errors/skips; 16/16 mutants killed** under fresh `finish-v8` artifacts. `p8-finish-v8-mock-20261027`: **PASS**, 24 dialogues / 80 turns / 80 reviews / 240 fake requests, zero protocol failures. All 19 guarded network-record groups report zero denied external connections; real calls/spend **0 / $0**. Broad repository and unchanged Java/frontend checks were **NOT_RUN** in the v8 round.

## Scripts and negative evidence

Each lecture has dialogues `-1` (definition/explanation, 3 turns), `-2` (Socratic prompts and a learner reply, 3 turns), and `-3` (comparison and a related absent-topic follow-up; the union-bound dialogue is entirely expected-abstain). Every dialogue contains “Why is that?” and another elliptical/reply follow-up. Expected prior topics are passed only to the independent reviewer. They are never supplied to the Tutor. The scripts have 56 context-dependent follow-ups, 11 insufficient-evidence turns and 24 Socratic turns in eight dialogues.

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

**User-approved correction (t44s14):** the probability-l1 corpus/snapshot contains no union-bound evidence (zero literal “union” hits), so abstaining is correct. V7 inherits v6’s `probability-l1-3` turns **1–3**: `expected_insufficient: true` and `zero_hit_terms: ["union"]` mirror existing should-abstain entries. They now contribute to `no_evidence_abstain_rate` and cannot count as over-abstention. Turn **4** already expects abstention for its absent Dirichlet extension and remains byte-identical. Learner text, every other dialogue/turn and all thresholds are unchanged; tests compare parsed JSON and raw bytes against `970bd00`. The former “left for the user to decide” issue is resolved in v6; historical trials remain unchanged.

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
| context_retention_rate | ≥0.90; reviewer plus v7 deterministic context rules on follow-ups |
| socratic_compliance_rate | ≥0.75; guiding question/hint, no full-answer dump |
| protocol_failure_rate | ≤0.05 per learner turn |
| p95_turn_latency_s | ≤20; nearest rank, Tutor execution only |
| max_calls / max_usd | 400 / $0.70, reviewer included |

Summary also reports `metrics.over_abstain_count`, `metrics.over_abstain_rate` and `over_abstain_turns` as `(dialogue_id, ordinal)` pairs. The numerator counts completed `insufficient_evidence` outcomes where `expected_insufficient=false`; the denominator is all attempted turns with that script label, including failures. Empty denominator yields zero. Additional `metrics.over_abstain_cascade_count` / `over_abstain_cascade_turns` report the subset immediately preceded by a failed/unpublished turn; `metrics.over_abstain_non_cascade_count` / `over_abstain_non_cascade_turns` report the remainder. This is **report-only**: it adds no threshold and changes no verdict gate.

The reviewer prompt explicitly rejects invented antecedents after failed/unpublished prior turns, even for source-supported claims. Conversation history includes status/outcome. The runner deterministically downgrades answered context follow-ups in that situation, except explicit clarification questions. V7 corrects `context_retained` to true for the exact `ABSTENTION` contract with `outcome=insufficient_evidence`, or a clarification question recognized by the existing regex, even when the reviewer says false and regardless of the previous turn’s publication status. This covers chains of published abstentions. Support, Socratic and clean-abstention judgments remain untouched. All attempted context follow-ups, including expected-abstain turns, stay in the denominator; failed turns and missing/failed reviews remain misses. `summarize()` is unchanged. Conservative clarification recognition and model review still need real-model evaluation.

All 24 dialogues/80 turns and all gates are required for PASS. Nonfatal quality/protocol misses are PARTIAL. Fabricated citations, channel/ledger errors or unknown outcomes are FAIL. Missing/failed reviews count as unsupported, not successful. Citations in malformed proposals are inspected before schema validation so malformed output cannot hide invented IDs. An insufficient-evidence candidate containing substantive text is rejected by the runtime, never rewritten into a passing answer.

The P8 channel derives from P7's reserve-before-send pattern with separate `p8_tutor_real_run/p8_tutor_real_event` PG tables. It preserves an append-only fsynced JSONL mirror, exclusive locking, durable PG commit and exact record comparison before dispatch. No transport/schema retry and no automatic ledger repair. Runtime tool-error observations permit another model-selected attempt within the bounded persistent turn budget described above; each decision is separately accounted. Unknown/failed outcomes consume the full reservation and cannot be replayed. Actual usage exceeding reservation blocks the run. There is no product adapter importing this channel.

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
  --database-port 25741 --network-records .data/p8-tutor/checks/ctx-v7-full-safe-network \
  -- -q \
  -k 'not (test_live_requires_both_switches or test_live_schema_failure_never_enters_chatprovider_repair or test_key_never_in_exception_logs_or_ledgers or test_parallel_tool_calls_execute_first_only_without_extra_request or test_parallel_tool_calls_with_unknown_tool_fail_closed)' \
  --junitxml=../.data/p8-tutor/checks/ctx-v7-full-safe.xml
```

Standalone default mock run; never use the external ledger path for mocks. These examples record completed runs; choose fresh run IDs, ledger paths and artifact labels for reruns:

```bash
uv run --project agent-service --offline python .data/p8-tutor/checks/run-guarded-tutor.py \
  .data/p8-tutor/checks/v9-final-mock-network \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger .data/p8-tutor/ctx-v9-final-mock-ledger.jsonl --max-calls 400 --max-usd 0.70 \
  --run-id p8-ctx-v9-mock-final-20261027
python3 .data/p8-tutor/p8-ctx-v9-mock-final-20261027/sample.py -n 5
```

Mutation verification (all fake, separate PG, inherited network guard; outputs under `.data/p8-tutor/checks/`):

```bash
uv run --project agent-service --offline python eval/p8-tutor/run-repair-mutations.py --label v9
```

The v9 mutants retain v7 coverage of silently dropping unobserved IDs, silent truncation to four, trusting provider declarations, unlimited format repair, removal of the deterministic reviewer cascade downgrade, always-zero cascade reporting, immediate size/Socratic failure, missing repair reservation and always-zero total over-abstention, including the abstention/clarification context non-penalty and reviewer retry. V8 adds missing keep/remove guidance, silent removal of excess inline IDs/text, and math brackets counted as citations. V9 adds `citable-last-search-only` and `citable-includes-prior-turn-citations`. Each must yield exactly one failed test and zero errors/skips, followed by byte/digest restoration. Prior output paths are refused.

Outputs: `dialogues.jsonl`, `reviews.jsonl`, `summary.json`, and standalone `sample.py`. Sampling prints N seeded dialogues with turns, outcomes, inline citations and full cited source text. Summary explicitly labels fake runs `NOT_RUN_MOCK_MECHANICS_ONLY`. Fake transport does not read credentials; its fixed reviewer judgments and negative responses only verify mechanics.

## Exact live command for a later reviewer — DO NOT run in this task

The human operator must separately configure credentials and the required live opt-in in their shell. The application never loads private env files or sets the opt-in. This requested full-suite command is **documentation only**, with a fresh run ID/ledger and no dialogue filter:

```bash
cd /home/dev/projects/lecturelens-p8-tutor-protocol
uv run --project agent-service --offline python eval/p8-tutor/run.py \
  --live \
  --dsn 'postgresql://p8:p8-local-only@127.0.0.1:25741/lecturelens_agent_acceptance' \
  --ledger /home/dev/lecturelens-eval/deepseek-20261027/ledger-p8-ctx-v9-full-20261027.jsonl \
  --max-usd 0.70 --max-calls 400 --run-id p8-ctx-v9-full-20261027
```

The command uses the unchanged $0.70/400-call policy. Worst-case five Tutor calls plus one review per turn would require 480 requests, so the ledger can stop the round before completion. Within four distinct inline IDs, declaration differences need no repair call; excess IDs still require repair. If v5's eight failed turns complete in their existing call counts, eight added reviews project 314 requests / about $0.513 at the v5 mean cost. Five Tutor calls plus review on every turn project about $0.784 and exceed both caps. These are estimates, not completion guarantees; conservative reservations and prompt length can stop the run earlier. See the report for assumptions.

`--dialogue-ids` remains available for focused diagnostics. It accepts space-separated unique frozen IDs; empty, unknown or duplicate IDs fail before ledger/provider entry. Focused summaries record `scope=focused` and selected IDs and return **PARTIAL** at best, even with perfect metrics. These are public development scripts, not fresh holdout data.

`AGENT_LLM_API_KEY` is read only inside the live sender; raw errors, body text and keys never enter the accounting ledger/logs. Key echoes in parsed or raw provider responses are rejected. All requests use the fixed HTTPS DeepSeek route, no redirects and no environment proxy. Tutor transport requests are not retried; independent reviewer protocol/request retries follow the three-attempt rule above and consume the same caps. To check consistency without sending/reading the key, add `--check-ledger` with the same run ID, caps and candidate. Each run ID is single-use; restart cannot reset its budget or resend an unknown call.

This round leaves the isolated PostgreSQL project running for reviewer inspection; the reviewer stops it and retains its volume.
