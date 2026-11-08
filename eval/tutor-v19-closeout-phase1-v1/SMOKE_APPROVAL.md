# Sole proposed v19 smoke — awaiting explicit paid approval

Use the unchanged frozen plan `../tutor-selection-v19-v1/SMOKE_PLAN.md`, candidate
and three-turn packet; `EXECUTION_BINDING.json` binds their hashes and code commit.
The recovered checkout is `/home/dev/.codex/worktrees/tutor-v19-closeout-20261108`.
Default `agent-service/.venv/bin/python scripts/dev/run_tutor_smoke_v19.py` verifies
only; no transport, database, credential or model call is required.

Proposed exact scope, **not authorization**:

- Model `deepseek-flash`, endpoint `https://api.deepseek.com/chat/completions`;
  temperature0, thinking disabled, required tools, parallel_tool_calls=false.
- The original three ordered exposed development turns: complete explanation/
  changed-example commented code/indexing; withheld-answer indentation hint;
  specific correction/feedback using real prior history. No SQL, holdout or full16.
- At most3 ordinary model decisions plus1 **shared** finish correction per turn,
  4 sends/turn,12 total. Format and span/support cannot each add a correction.
- At most4096 output tokens/request; body4096/evaluation1024 Unicode code points
  with all labels/full IDs. Existing deadline, source, wire, runtime/session caps.
- Concurrency1, transport retries0, reviewer0, embedding0. No automatic parameter
  changes, reruns, replacement invocation, skipped-turn refill or expansion.
- Local reserved plus settled liability <=US$0.30, including failed/unknown calls.
  Conservative rates300 input/1200 output nano-USD/token. Worst reservation:
  `12*(65536*300+4096*1200)=294912000` nano-USD =US$0.294912. This is a local
  liability bound, not a guaranteed supplier invoice or billing hard cap.

Official [pricing](https://api-docs.deepseek.com/quick_start/pricing/) and
[Chat API configuration](https://api-docs.deepseek.com/api/create-chat-completion/)
were checked on2026-11-08 at14:49 Shanghai time; the proposed conservative rates
still cover published peak rates. Exact API model ID remains `deepseek-flash`;
published backend is DeepSeek-V4.1-Flash-1017, a moving alias. No account/balance/
model API, credentials or provider was accessed. Recheck public facts if the receipt
is older than24h or documentation changes before authorized execution. The current
API page does not document parallel_tool_calls; false is sent, but provider compliance
is not guaranteed. Existing bounded parsing validates all returned calls, executes
only the first and counts dropped ones without another request.

Any future authorization must bind final clean Git HEAD, frozen candidate/packet
hashes, exact model and bounds,3+1 shared allowance, expiry and unique v19 run ID.
Both original grant templates remain unauthorized. A single-use claim and durable
mirrored reservations must precede dispatch. No valid grant is created by this file.

Stop the entire invocation at the first provider/protocol/usage/model, authority/
source/citation, deadline/budget/ledger or failed-correction error. Unknown usage
retains liability. Preserve failed, skipped and unobserved positions. After successful
mechanical execution, review every required point, code, condition, citation support,
feedback and Socratic withholding against the original reference/source; real source
plus wrong explanation is FAIL. There is no automatic semantic reviewer between
successful mechanical turns. Review is same-author Codex AI review, not independent
human blind assessment. Any semantic FAIL precludes recommending full16.

Retain execution HEAD/code and manifest hashes, raw decoded request/response bodies
with redaction metadata, usage/cache observations, events, PG state, mirrored local
ledger and one-use claim. Supplier actual charges remain UNKNOWN without an invoice.
Existing historical raw bodies are unavailable and will not be fabricated; this is
a fresh bounded smoke proposal, not their reproduction. Even3/3 would supply only
preliminary evidence for a further decision, never automatic expansion or release.

Real quality improvement, cost optimization, independent human agreement, SQL
holdout, expansion and learning effects remain NOT_RUN. Stop and seek explicit paid
approval before any dispatch.
