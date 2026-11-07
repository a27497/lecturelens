# Tutor scale evaluation preparation

This is **synthetic evaluation preparation**, not a real Tutor quality evaluation.
No external model, embedding, data-generation or model-review calls are needed for Mock execution.
No production/student data, existing acceptance accounts, Java/MySQL writes or deployed configuration are used.
Historical P8 v9, P7, AU manifests and results remain unchanged. See [the verification record](REPORT.md).

## Dataset and boundary

`dataset.py` verifies `dataset-lock.json`; runtime preflight also verifies the original P8 frozen candidate and
this directory's `candidate.json`. `author.py` is the auditable, original English fixture source.
`development.json`, `holdout.json` and `snapshot.json` are checked-in reproducible projections, not fetched content.
All material is original **fictional microcourse** content dedicated under **CC0-1.0** for this evaluation.
There are no third-party extracts or unstated source licenses. A source locator is a JSON Pointer into
`snapshot.json`, with course, numbered section, exact text and SHA-256. The compatibility millisecond fields
encode section slots and **are not media timestamps**. To reproduce projection bytes, copy this directory to
an empty scratch location, remove only its generated JSON files and run `python dataset.py build` there;
never overwrite a frozen candidate or a previous trial.

| Partition | Course | Sessions | Learner turns | Distinct evidence sections |
| --- | --- | ---: | ---: | ---: |
| development | Synthetic Queue Operations | 16 | 80 | 16 |
| development | Synthetic Field Sampling | 16 | 80 | 16 |
| development | Synthetic Archive Workshop | 16 | 80 | 16 |
| holdout | Synthetic Energy Bench | 16 | 80 | 16 |
| total | 4 courses | 64 | 320 | 64 |

A course is one closed evidence collection; a session is one independent five-turn conversation; a turn is
one learner message plus its scheduled Tutor result (success, failure or missing). Search/reviewer calls are
not additional dialogue turns. Each session has a distinct substantive scenario and five individually authored
questions: factual explanation, contextual application, false premise, a parameter absent from the material,
and an outside-course request. All 320 learner messages are distinct. Repeated category structure is a sampling
design, not 320 independent topics or 320 successful answers. No new Socratic-quality claim is made by this set.

Every turn contains reference section text, an exact locator, expected behavior and a rubric. The first three
turns require supported reasoning and inline attribution, including units/conditions and cross-turn referents;
the third must explicitly correct the false premise. The last two require clean abstention, with no invented
parameter or substantive outside-course answer. Reference text can justify simple arithmetic derivations;
reviewers must check the actual reasoning, not exact output wording. Topic/negative/reference labels are never
sent to the real Tutor. They are used by the explicitly oracle-like Mock responder and independent evaluator.
A deterministic copy of a retrieved paragraph is not a semantic answer to the question.

`holdout-manifest.json` freezes the Energy course and session list before real evaluation. That course is
withheld from product/prompt tuning; this task changes neither. Mock trials consume no semantic quality outcome.
Public synthetic material does not establish that the base model never saw a concept. After the first future
real holdout trial, retain all failed trials and do not tune on those results; another candidate needs a fresh
course holdout. The current tiny, synthetic corpus does not establish natural-course generalization.

## Server execution (Mock defaults)

Use a fresh run name and output directory for every invocation. Outputs and ledgers refuse reuse. Commands
below run from the repository root. Dependencies follow `agent-service/uv.lock`; offline sync works only if
all locked packages are already cached. No model download is needed.

```bash
uv sync --project agent-service --frozen --offline
COMPOSE_DISABLE_ENV_FILE=1 docker compose -p lecturelens-tutor-scale-prep-20261107 \
  -f eval/tutor-scale/compose.yaml up -d --pull never
# First start only; creates a second database for mechanism tests.
docker exec lecturelens-tutor-scale-prep-20261107-postgres-1 \
  psql -U tutor_scale -d lecturelens_agent_acceptance -c 'CREATE DATABASE lecturelens_agent_test'
python3 eval/tutor-scale/dataset.py
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py \
  .data/tutor-scale/network-smoke-NEW eval/tutor-scale/run.py \
  --smoke --output .data/tutor-scale/smoke-NEW
agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py \
  .data/tutor-scale/network-full-NEW eval/tutor-scale/run.py \
  --output .data/tutor-scale/full-NEW --max-calls 1200 --max-usd 2.80
```

For supervised long checks use `scripts/dev/run_check.py` and the supplied process guide. The base commit's
supervisor predates bounded cleanup: this task uses a temporary **committed** `b82bebf` version in
`.data/dev-tools/scripts/dev/run_check.py` with `--cwd "$PWD" --output-root .data/dev-checks --timeout 300 -- COMMAND`.
Its exact source hash and provenance are in REPORT.md. This is not an import of another worktree's edits.
Cancel only the new supervisor after matching its PID/start ticks and wait for its terminal record.

Only the new compose project is used (loopback 25841; dedicated synthetic role `tutor_scale`, owner 811007;
0.5 CPU/384 MiB). No browser or persistent human login is provisioned. Stop only that project with
`docker compose -p lecturelens-tutor-scale-prep-20261107 -f eval/tutor-scale/compose.yaml stop postgres`.
Preserve its volume and trial files. Never clean other projects or databases.

The safe launcher strips provider/proxy/tracing environment and installs the existing Python socket fence;
startup fails if the fence is absent. Default `--live=false` additionally requires `httpx.MockTransport` and
never reads a provider key, even if the invoking shell has one. Fake usage and all fake reviewer labels are
marked MOCK. `config.json` records code SHA, frozen candidate identity, dataset lock/version and bounds;
`turns.jsonl` contains every scheduled turn, script, result, proposals, citations and associated calls.
Each course shard retains raw turns, per-request `calls.jsonl`, fsynced `ledger.jsonl` and PG accounting.
The PG Tutor store additionally persists tool observations/checkpoints. Summary reports scheduled/status/error
counts; missing turns become explicit `MISSING / RESULT_MISSING` rows. Failures, timeouts, failed reviews and
missing rows cannot complete the suite or disappear from the scheduled denominator. An incomplete run exits 1.

Four serial shards each receive one quarter of the requested call/USD ceilings. Defaults are 300 calls and
$0.70 reservation per course (whole invocation <=1200 calls / $2.80). The frozen channel hard cap remains
400 calls / $0.70 per shard; larger inputs are rejected, not silently capped. Runtime per-turn limits and
20-second deadline remain unchanged. Every request reserves before send; unknown/failed outcomes retain the
reservation and cannot be replayed. A blocked shard stops; later shards may run within their allocated budget.
No budget transfers or automatic resume. Mock's legacy dollar arithmetic is a ledger test, **not billing**.
Inject a bounded synthetic first-call timeout/malformed response with `--smoke --fault timeout` or
`--smoke --fault malformed`; use `--max-calls 4` for a budget-stop test. These must remain incomplete.

## Future explicit real trial (NOT_RUN here)

Do not use the socket-fenced launcher for real requests. A separately authorized operator would supply
`--live`, `LECTURELENS_REAL_EVAL=1`, a credential in process environment, a **new output path**, and `--pricing`.
Neither the program nor these tools load secrets files or configure keys. Missing CLI opt-in always stays Mock;
missing environment opt-in or compatible pricing fails before ledger/send. Never put keys in arguments/logs.

The pricing JSON must contain `currency: "USD"`, `verified_at`, a supporting HTTPS `source_url`, and
`rates_usd_per_million: {"deepseek-flash": [0.30, 1.20], "deepseek-v4-pro": [1.74, 3.96]}`. These numbers are
**inherited historical reservation ceilings**, not verified current prices. Before a future trial an operator
must independently verify they safely cover current billing. Different prices/routes require a new candidate;
no file can override the frozen channel's rates or ceilings. No valid current pricing artifact is supplied here.

The future command shape is `python eval/tutor-scale/run.py --live --pricing OPERATOR_PRICING_JSON
--output .data/tutor-scale/real-UNIQUE --max-calls 1200 --max-usd 2.80` with the explicit environment opt-in.
It is documentation only, not authorization to execute in this task. Generation and review use the existing
isolated P8 channel/route, reserve-before-send, bounded retries and durable PG/JSONL accounting. The same full
scope, failures and held-out boundary apply. Larger natural documents may exhaust conservative reservations
before completion; caps never guarantee completion. Failed sessions remain failures.

Per-call fields include requested model, returned model/version and optional system fingerprint, status/error,
prompt/completion tokens or null, usage source, latency, pricing provenance and billing status. An upstream
alias is recorded as an alias, not an immutable vendor revision. Missing version/usage remains explicit;
unknown calls are not assigned zero tokens. MOCK tokens never count as real consumption. `billed_usd` and
cost status stay `null / NOT_RUN` until actual billing and defensible pricing are reconciled; this task
implements the comparison interface, not an invoice estimator. Compare only matching dataset lock/scope,
including failed calls, and retain per-call pricing provenance.

## Preregistered blind review

Before viewing outputs, the fixed seed **20261107** selects five of sixteen turns within each of twenty
course × category strata: **100 unique turns per candidate** (75 development / 25 holdout). One selected turn
per stratum forms a **20-turn independent overlap**. Reviewer A is the primary 100-turn annotation; reviewer B
receives those 20 turns independently. With multiple candidate runs the identical selected turn IDs are used
and all candidate items are mixed in independently shuffled A/B packets. Thus two systems create 200/40
assignments, not 100 independent tasks per system pair. No replacement after seeing a failure.

```bash
python3 eval/tutor-scale/blind.py export --runs .data/tutor-scale/full-NEW \
  --output .data/tutor-scale/blind-NEW
python3 eval/tutor-scale/blind.py import --key .data/tutor-scale/blind-NEW/private-key.json \
  --packet .data/tutor-scale/blind-NEW/packet-A.json \
  --ratings .data/tutor-scale/blind-NEW/annotation-A.json \
  --output .data/tutor-scale/blind-NEW/import-A.json
# Independently repeat for B, then recompute:
python3 eval/tutor-scale/blind.py score --key .data/tutor-scale/blind-NEW/private-key.json \
  --imports .data/tutor-scale/blind-NEW/import-A.json .data/tutor-scale/blind-NEW/import-B.json \
  --output .data/tutor-scale/blind-NEW/scores-NEW.json
```

Only give each reviewer their `packet-X.json` and `annotation-X.json`. The private key (0600) maps opaque item
IDs to runs/candidates and retains model review labels. Packets omit model/version/candidate/run identities and
model judgments; answer text is preserved, so an answer that self-identifies a model could compromise blinding
and should be logged before analysis. Reviewers must not share annotations or see the key until both submit.
Packets include prior conversation, failed statuses, exact cited text and reference rubric for evidence audit.
Source IDs are content based, identical across candidates. Separate exports are not a randomized comparison;
provide all candidate runs to one export. Mixed MOCK/REAL runs, smoke scopes, missing/duplicate turn records
and dataset mismatches are rejected. Packet hashes bind imports to exact displays; every assigned item must
remain present, with `complete:false` for missing annotation. No human labels are synthesized by export/import.

For each completed item set a reason and `overall_supported` to supported/unsupported/uncertain. Inventory
**all** substantive assertions from both answer and evaluation as exact text spans in `claims`, each with a
unique `claim_id`, `requires_citation` boolean and the cited `citation_ids` that actually support that assertion.
Nonfactual questions can have `requires_citation:false`; substantive assumptions still require citations.
Record one `citation_checks` row per claim–citation pair with `claim_id`, `evidence_id`, `label` and `quote`.
Supported judgments require an exact nonempty quote from that attached evidence. Every output citation must
be accounted for; do not import support from another turn or source. Pure abstentions have no claim/citation
pairs and are outside the support denominator; record `abstention_correct` separately. Cross-turn referent,
conditions and evidence consistency are recorded as `context_consistent` (true/false/null). Import validates
structure/locators, **not semantic correctness or completeness of human segmentation**. Reviewers attest to
complete assertion coverage with `complete:true`; disputed segmentation remains an audit issue. Resolve
adjudication separately after the original independent labels are saved; never rewrite them to increase agreement.

## Scoring units and missingness

* **Citation support accuracy:** supported claim–citation pairs / all annotated claim–citation pairs.
  Unsupported and uncertain are in the denominator and contribute zero supported pairs.
* **Citation presence coverage:** citation-requiring assertions with at least one attached citation /
  all annotated citation-requiring assertions. Presence alone says nothing about support.
* **Supported citation coverage:** citation-requiring assertions with at least one supported pair /
  all annotated citation-requiring assertions. One assertion with several citations counts once in coverage.
* **Model–human agreement:** P8 `answer_supported` boolean versus primary human `overall_supported`, per selected
  expected-answer turn. Both labels must be binary; uncertain, missing and failed reviews are excluded from
  agreement/kappa but reported as excluded alongside the entire eligible sample, never treated as agreement.
  Expected-abstain turns are outside this support comparison; a model's wrong abstention on an expected-answer
  turn remains eligible and must be reviewed as unsupported. No human label is auto-downgraded or overwritten.
* **Double-annotation agreement:** same overall-support binary unit on the 12 expected-answer turns among the 20 overlapping assignments, with
  the same explicit missing/uncertain handling. A is primary; B is not pooled into a larger independent sample.
* **Cohen's kappa:** `(p_observed - p_expected)/(1 - p_expected)`, using the two binary marginal distributions
  on exactly the comparable pairs. Zero pairs or degenerate identical marginals produce `null` with a reason.
  Do not apply binary kappa to token counts, ratios, incomplete labels or mixed scoring units.

All ratios expose numerator, denominator and sample size; zero denominators yield null. Citation metrics are
**observed annotated-subset metrics**, with assigned/annotated/missing turn counts shown alongside, not claims
about unannotated turns. Missing annotation contributes no fabricated claim units. Overall task completion,
missing executions and failed reviews remain separate full-scheduled-denominator statistics. Empty import
roundtrips return `human_scores_status: NOT_RUN`, null quality ratios and zero comparable pairs. A real human
score requires actual independent annotation. MOCK labels never become real human/model agreement or teaching
quality. `test_tools.py` checks accuracy/coverage 1/3, 2/3, 1/3 and binary agreement 0.75 / kappa 0.5 using only
hand-constructed labels; no actual outputs are relabeled to pass a gate.
