# Unapproved real execution sheet — fresh development v1

**NOT AUTHORIZED / NOT_RUN.** Prior paid willingness, prior USD limits and unused
allowance do not carry over. This sheet fixes a proposal, not spending permission.

| Item | Frozen/proposed value | Confirmation needed |
| --- | --- | --- |
| Candidate | `p8-tutor-grounded-v11-development`; manifest `b7fe50df1854703cc05d4ad039dad3245cc62adc5d68c3af7b394f2407f0ec58` | No candidate substitution |
| Base candidate code | `b96157fbd0107efd793a9fb03b17f1776a3ce8ea`, unchanged v11 source | Reverify chained candidate and new adapter hashes |
| Scope | `batch-plan.json`: parts A then B, 2 courses / 4 complete sessions / 16 turns | Confirm this exact batch; SQL excluded |
| API / provider | DeepSeek `deepseek-flash`, `https://api.deepseek.com/chat/completions` | Confirm API ID and moving-alias limitation; current access UNKNOWN |
| Version comparability | Same requested alias/settings as v11 old batch; actual future response identity UNKNOWN | Alias drift and generation randomness prevent a strictly controlled comparison |
| Settings | Temperature 0; thinking disabled; maximum output 1,200/request | Keep settings; returned ID does not prove an immutable backend version |
| Reviewer / concurrency | Off / 1, sequential complete sessions | No real reviewer requests or fake missing-review PASS |
| Retries | Transport 0, application transport 0, no SDK; redirects disabled | Keep zero; existing format/mode repair remains bounded and charged |
| Total requests | **Propose 80 maximum, NOT approved**; exact failure/repair requests included | User must provide total integer cap; accepted range 2–80 |
| Total local USD reservation cap | **UNKNOWN / UNCONFIRMED**, accepted tool range >0 and ≤0.70 | User must provide a new explicit total; ceiling is not authority or expected spend |
| Current price / account balance | **UNKNOWN**, not checked | User checks balance; refresh public pricing before any real invocation |
| Supplier actual-bill hard cap | **UNKNOWN / NOT GUARANTEED** by local ledger | User must confirm supplier protection or accept limitation explicitly |

For each turn: first model decision selects local evidence search, second chooses
finish: **16 × 2 = 32 normal requests**. A second search on every turn gives
**16 × 3 = 48**. Up to two existing repair decisions with two searches/finish gives
**16 × 5 = 80 maximum**. The runtime can stop sooner on deadline/token/session
bounds; neither completion nor that request pattern is guaranteed. Tools and
retrieval are local, with no embedding/provider-search calls. Reviewer, network
retry and SDK extra requests are zero. A rejected-before-send channel attempt is
reported separately from reserved/sent calls, not silently counted as a paid send.

The pinned eight-turn runner handles two complete sessions and ≤40 requests per
part. This batch has two fixed parts; an explicit total call cap is split in half
(remainder to B). The total integer nano-USD cap is split identically. Each part's
persistent PG/JSONL ledger enforces its allocation; **sum of allocations equals the
approved total**, with no transfer/replenishment. This can stop an otherwise cheap
whole batch early if one part needs more allowance. Sample membership never changes
because of a cap. Both complete part plans and all 16 expected turns are recorded
before requests; failure in A leaves B missing, never omitted from the denominator.

The inherited ledger reserves before send using serialized UTF-8 bytes and maximum
output at its historically frozen rate basis. Failed/unknown outcomes retain the
reservation; invalid/missing usage or blocked/pending accounting stops further
sends. The byte proxy is not a proven upper bound on all supplier framing or hidden
billing. Usage/rate changes can be detected only after an incurred request. Thus
local pre-reservation does **not** guarantee the supplier's actual invoice ceiling.
The adapter requires an actual-execution-date reviewed pricing file compatible with
its fixed basis; stale/incompatible rates block rather than quietly updating old
prices. Do not interpret historic constants as verified current pricing. Invoice,
current discounts/cache timing and balance remain unknown; no billing API is queried.

No automatic run is scheduled. After the user confirms this exact model/alias
limitation, numeric total requests, explicit total USD amount and billing limitation,
verify the isolated DB again and instantiate **all** placeholders below. They are
intentionally non-runnable authorization placeholders, not defaults:

```bash
LECTURELENS_REAL_EVAL=1 PYTHONPATH=agent-service/src \
  agent-service/.venv/bin/python eval/tutor-fresh-dev-v1/batch_run.py --live \
  --agent p8-tutor-grounded-v11-development --model deepseek-flash \
  --reviewer off --concurrency 1 \
  --max-calls '<USER_CONFIRMED_TOTAL_REQUESTS_AT_MOST_80>' \
  --max-usd '<USER_CONFIRMED_TOTAL_USD_GT_0_AT_MOST_0.70>' \
  --pricing '<ACTUAL_DATE_REVIEWED_COMPATIBLE_PRICE_OBSERVATION_JSON>' \
  --ack-ledger-not-billing-cap \
  --output '.data/tutor-fresh-dev-v1/<GLOBALLY_UNIQUE_AUTHORIZED_RUN>'
```

Credentials are provisioned separately, never in argv/logs. Do not use the Mock
socket launcher for live calls; its external fence must reject them. No availability
probe, account query or paid request is part of the present task. The technical
switches do not establish conversational spending authority.

Stop on first auth/model/protocol failure, failed/unknown turn, cap, missing usage,
pending/blocked/divergent ledger or cancellation. Preserve partial calls/answers,
all failed/missing outcomes and unknown consumption. No model fallback, prompt
change, result-driven data edit, top-up, retry batch or automatic resume. A new run
requires separate authorization; never reset a ledger to resend an unknown request.
Afterward perform the frozen full source review with `grading-rules.json`, keeping
material uncertainties and all 16 denominators; stop and report even if the gate
fails. Do not tune on this batch and present it as independent generalization.

Old-eight-turn metrics are context only: the new tasks, conversation lengths,
context and claim inventories differ, so a raw score difference is not a paired
improvement estimate. SQL, 60/320 turns, independent human agreement, real reviewer,
learning effects and cost optimization remain outside this execution sheet.
