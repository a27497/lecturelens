# Frozen eight-turn pilot: execution checklist, awaiting authorization

This single-purpose evaluation adapter reuses the existing P8 channel, persistent PG/JSONL ledger,
SnapshotAuthority, TutorProvider/Store and result reconciliation. It explicitly instantiates the frozen
`PythonTutorRuntime`; product defaults, historical drivers and frozen assets are unchanged. No real
request or account query has been made. The old public driver is Mock-only; the old synthetic live driver
uses v9 and automatically reviews answers, so neither is a shortcut for this pilot.

## Confirmation sheet

| Item | Proposed/frozen value | Confirmation |
| --- | --- | --- |
| Provider / route | DeepSeek / `https://api.deepseek.com/chat/completions` | User must confirm |
| Tutor API ID | `deepseek-flash` | User must confirm |
| Version | Public docs: `DeepSeek-V4.1-Flash-1017`; moving alias, immutable API ID unverified | Accept alias limitation or block trial |
| Agent | `p8-tutor-python-notation-v10-development-r2` | Fixed; explicitly selected |
| Candidate SHA-256 | `8f430ba637bb13dfd415bf29d4785e116d44141d7d3c49946ede77cee45079cf` | Checked before DB/egress |
| Dataset | `tutor-public-v1`; Python `python-01` + spreadsheets `sheets-01`, 4 + 4 turns | Fixed; no SQL |
| Scope SHA-256 | `27c3361d841412f950b9aac5ab08a0d14e40b4fb0bc60801be0c9d181e5180d7` | Checked before DB/egress |
| Data-lock SHA-256 | `4645c31d7e3eff19aa534714613d3ead64c1a7fcefcccba463fdbe9ef77f4620` | Checked through frozen preflight |
| Reviewer / concurrency | **Off / 1**, no worker thread | Fixed; reviewer route rejects before reservation/credential lookup |
| Provider-output cap | 1,200 tokens/request; thinking disabled, temperature 0 | Confirm proposed settings |
| Transport/application/SDK retries | **0 / 0 / none**; HTTP redirects disabled | Confirm |
| Format/mode repairs | Existing controller retains its bounded repairs; included below | Confirm |
| Total provider-request cap | **Proposed 40**, not authorized; accepted range 1–40 | User must provide explicit integer |
| Local ledger USD cap | **UNCONFIRMED**; explicit positive amount at most inherited USD 0.70 ceiling | User must fill; ceiling is not authorization |
| Supplier bill hard cap | **UNVERIFIED**; this adapter cannot guarantee it | User must confirm provider-side protection or explicitly accept limitation |
| Account balance / access | **UNKNOWN**; not queried | User checks balance; access only verified by first authorized request |

Model selection comes from the frozen paid channel's `MODEL`/`ROUTE` allowlist, not product environment
defaults. Other IDs/providers require a separately reviewed adapter/rate change; no automatic fallback.
Returned model/fingerprint metadata is recorded but may remain an alias or be missing; it is not an
immutable backend pin. The [official changelog](https://api-docs.deepseek.com/updates/) explicitly describes
`deepseek-flash` as the route to the latest model. No `/models` or authenticated availability probe was sent.
Any real availability check is part of the paid pilot and counts against its cap.

## Request arithmetic

Each turn first sends a model request to choose local evidence search, executes that deterministic local
tool, then sends another request to choose finish: **8 × 2 = 16** normal HTTP requests. A second local search
adds a model round trip: **8 × 3 = 24**. One format repair and one mode repair may each add a fresh model
decision: **8 × (2 searches + 1 finish + 2 repairs) = 40**. The runtime enforces its five-call turn bound;
deadlines/token caps may stop sooner. Tool execution is local, without embeddings or provider search APIs.
Reviewer calls/retries are zero. There is no SDK; raw HTTPX uses `HTTPTransport(retries=0)`, and the Tutor
channel has no transport/schema re-ask retry. Controller repairs are new charged decisions, not free retries.

One ledger covers both sequential sessions. A reservation consumes a call even if delivery is uncertain.
Channel-attempt records can include an additional **rejected-before-send** attempt after a cap is reached;
these are distinguishable from reserved/sent calls. No paid request exceeds the configured call cap.
Choosing a small cap does not select a smaller sample: all eight turns remain expected, with failures/missing
preserved after an abort. The 16/24/40 paths assume the runtime continues; completion is never promised.

## Price observation and budget limitations

[pricing-observation-20261107.json](pricing-observation-20261107.json) records public-document inspection on
**2026-11-07 UTC**, not account pricing or spending approval. According to the
[official pricing page](https://api-docs.deepseek.com/quick_start/pricing/), Flash prices in USD per million
tokens are: input cache miss **0.30 peak / 0.15 off-peak**, cache hit **0.006 / 0.003**, output **1.20 / 0.60**.
The adapter uses peak cache-miss rates for conservative local accounting regardless of clock/cache state.
Live preflight requires a same-UTC-date price observation compatible with the frozen Tutor rates; stale
or changed rates reject execution. Refresh into a new reviewed observation rather than editing old evidence.
The old Pro reviewer fee constant is irrelevant because that route is prohibited.

Before every send, the inherited ledger reserves integer nano-USD:
`R = UTF-8 request bytes × 300 + maximum output tokens × 1200`.
It checks aggregate latest charges/reservations and the call cap under file/PG locks; mirrored content must
match, file fsync and PG commit precede sender control. Any pending reservation blocks another send.
Success settles against provider-reported tokens at those rates. Failed/unknown calls retain at least the
entire reservation; missing/invalid usage fails the call. Usage above reservation durably blocks later calls.

This enforces a **local reservation/estimated-cost limit**, not the supplier's actual bill. Raw bytes are a
conservative input proxy, not a proven upper bound for provider chat/tool framing or hidden accounting;
prices/alias can change and failure usage may be unknown. An overshoot is detected after that call has
already incurred any fee. No invoice/billing endpoint is queried. Even the loose wire-size bound is
`65,536 × 300 + 1,200 × 1,200 = 21,100,800` nano-USD per request; 40 such reservations sum to USD **0.844032**,
above the inherited ledger ceiling. Actual runtime input/turn limits are tighter, but no completion or bill
guarantee follows. No dollar amount is proposed or authorized by this arithmetic.

## Commands and stop/recovery rules

Read-only preparation is the default: it verifies adapter, scope, candidate, data and historical hashes,
without opening a database, constructing HTTP transport or reading provider credentials:

```bash
agent-service/.venv/bin/python eval/tutor-pilot-v1/pilot_run.py \
  --plan eval/tutor-python-contract-v1/development-pilot-v1.json \
  --agent p8-tutor-python-notation-v10-development-r2 --model deepseek-flash
```

**Template only: do not run until the user explicitly authorizes the exact model and both caps.** The quoted
placeholders deliberately fail validation. Credential provisioning is outside this task; never put secrets
in commands/reports. Refresh/review public pricing on the actual execution date if different. Only after
verifying the dedicated evaluation DB/container/volume/port may this template be instantiated:

```bash
LECTURELENS_REAL_EVAL=1 agent-service/.venv/bin/python eval/tutor-pilot-v1/pilot_run.py \
  --live --plan eval/tutor-python-contract-v1/development-pilot-v1.json \
  --agent p8-tutor-python-notation-v10-development-r2 --model deepseek-flash \
  --reviewer off --concurrency 1 \
  --max-calls '<USER_CONFIRMED_TOTAL_REQUESTS_AT_MOST_40>' \
  --max-usd '<USER_CONFIRMED_LEDGER_USD_GT_0_AT_MOST_0.70>' \
  --pricing '<SAME_DAY_REVIEWED_PUBLIC_PRICING_JSON>' \
  --ack-ledger-not-billing-cap --output '.data/tutor-pilot-v1/<NEW_AUTHORIZED_RUN_ID>'
```

The frozen scope's original `execution_authorized: false` is preserved: the scope itself grants no spending
permission. Future authorization must be explicit and external; CLI/live-switch/caps provide technical gates,
not evidence that this conversation authorized payment. No execution mode is selected by default.

Abort the entire run on any failed turn, timeout, malformed/missing usage, fabricated citation, exhausted
call/money budget, pending outcome, ledger divergence or cancellation. Do not continue the other session,
switch models or replenish limits. Every run writes its expected eight turns before execution, then partial
and reconciled records, raw call metadata, config/SHAs, summary and the mirrored ledger. Missing reviewer
labels remain `DISABLED_NOT_RUN`; complete mechanics never means quality passed.

No automatic restart or replay is provided. Existing output/run IDs reject reuse. After interruption, inspect
expected versus partial records and PG/JSONL content plus pending reservations; absence of a result is not
proof that a supplier did not execute it. Preserve unknown charges and all failures. A fresh run or any
additional spending needs new user authorization; do not reset or repair the ledger to unlock it.

Mock verification uses the existing socket-fenced launcher and only fresh synthetic scopes in the verified
dedicated evaluation DB. Mock caps and token/fee fixtures are not real usage or authorized money. See
[REPORT.md](REPORT.md) for actual checks. Real calls/quality/human agreement/token usage/cost/learning outcomes
remain **NOT_RUN**. Public text capabilities do not establish video, ASR or Chinese-course performance.
