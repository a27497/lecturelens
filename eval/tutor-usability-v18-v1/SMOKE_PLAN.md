# One three-turn development smoke — proposal, not authorization

No real requests have been authorized or sent. The entry defaults to verify-only:
`agent-service/.venv/bin/python scripts/dev/run_tutor_smoke_v18.py`.
`--mode mock` uses an explicit Mock transport plus loopback PG and the actual
candidate/ledger/capture chain. `--mode live` requires a fresh grant and current
nonsecret documentary price/config receipt before DB, transport or key access.
The product factory remains **Mock-only**; paid egress exists only in this explicit
smoke entry. Never reuse the old full16 grant or execute full16 automatically.

## Exact proposed scope

- API model ID **`deepseek-flash`**, endpoint `https://api.deepseek.com/chat/completions`;
  temperature0, thinking disabled, required function tools, parallel_tool_calls=false.
- Three ordered **development** positions in `sample-candidate.json`: full explanation /
  changed-example code and indexing; withheld-answer indentation hint; correction of
  an explicitly wrong learner reply with full prior history and feedback.
- Codex authored/reviewed the questions, references and implementation. The source
  review is transparent, nonblind AI self-review, **not independent human gold**.
  Formal human agreement is NOT_RUN and is not made a prerequisite for this small
  development smoke. No SQL or holdout data is selected. Existing strict obligations
  and all historical FAIL are preserved; this new packet is separately versioned.
- At most **3 ordinary model decisions per turn** (including searches/support
  corrections), at most **1 format repair** per turn, **4 sends/turn and12 total**.
  No extra provider/reviewer/embedding calls, transport retries, parameter search,
  repeat attempts or reruns with a fresh budget. A request selecting a search is a
  paid model request too. Initial search then finish normally means6 total requests;
  this is an expectation, not a completion guarantee.
- **4096 output tokens per request**, including schema arguments/anchors,20s bound,
  request body<=65536 bytes, response entity<=131072 bytes. At most2 evidence searches
  per turn; existing session/runtime proxy caps remain.
- Local **reserved + settled liability <=US$0.30 (300000000 nano-USD)**, maximum12
  sends. No-cache peak rates300 input/1200 output nano-USD/token. Worst wire-based
  reservation: `12*(65536*300 +4096*1200)=294912000` nano-USD (**US$0.294912**), below
  the cap. Actual usage settles known outcomes; unknown/malformed/canceled outcomes
  retain full reservation unless usage is actually known. Unknown is never zero.
  Local accounting is conservative, not a supplier invoice or a guaranteed bill.

The [official pricing page](https://api-docs.deepseek.com/quick_start/pricing/)
was checked on2026-11-07: Flash API ID, published DeepSeek-V4.1-Flash-1017 backend,
peak input US$0.30 / output US$1.20 per million tokens. The
[official Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
documents the chosen fields. This is documentation review only: no account,
models/balance API, credential read or provider availability call. A new receipt
within24h before dispatch must confirm these rates cover current prices and
published configuration. Alias backend identity/account access remain unverified;
a returned model mismatch stops the run after retaining its usage/capture.

## Frozen execution and stop protocol

The manifest binds exact code commit, explicit code/tests/material hashes, parent
manifest and full tracked source roots. Default verification is read-only. A live
grant must bind the final clean Git HEAD, candidate/packet hashes, model,12 requests,
4096 output tokens, US$0.30, expiry and a unique `v18-...` run ID. A durable exclusive
single-use claim and mirrored fsynced PG/JSONL reservation precede each send.
A failed/unknown run cannot simply resume by resending. One invocation only.
The template is deliberately `authorized:false` with no grant ID/expiry/approved HEAD.
It is not permission and cannot dispatch.

Stop the **whole smoke** on the first engineering/protocol/provider/usage/model,
authority/citation, deadline, ledger, budget or correction failure. Preserve the
root code and all scheduled positions as completed/failed/skipped/unobserved;
never count dependent skipped positions as model errors or successes. Unknown
usage keeps full liability and blocks any further sends. No retries are automatic.

Mechanical completion does not grade content. After these3 positions, inspect
all answers/feedback/necessary points and every substantive addition against the
frozen reference/source, with explicit same-author AI review disclosure. Unsupported
content, wrong code/trace, omitted condition/point, over-refusal, solution in hint,
binding error or overlength is FAIL. All3 must satisfy every applicable criterion;
no denominator reduction. Any quality FAIL prevents recommending full16. There is
no automatic semantic evaluator or manual human checkpoint falsely claimed here.
Even a successful small smoke does not authorize full16, scaling or a release.

## Artifacts and next approval

Retain private `execution.json` (actual Git HEAD/code commit), `owner.json`,
`outcomes.json`, `runtime.json`, `summary.json`, `calls.jsonl`, `ledger.jsonl` and
`wire/*-{request,response}.body` plus capture metadata. Bodies are decoded HTTP
entities before JSON parsing, not TLS frames; known authorization strings are
redacted, headers/exceptions omitted, files0600/private directories. Partial and
redacted captures are labelled. Reference_points/scoring never enter product messages.
Preserve live PG schema/ledger and the one-use claim for reconciliation; clean
only an owned disposable Mock schema. No real browser/student/manual account is used.

Approve only this exact3-turn/12-request/US$0.30 one-shot scope if desired. This
phase stops before creating a valid grant or dispatching. Real quality improvement,
cost optimization, independent human agreement, SQL holdout, expansion and learning
effects remain **NOT_RUN**.
