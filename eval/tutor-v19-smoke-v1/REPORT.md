# Authorized v19 smoke: stopped at zero-cost preflight

**INCOMPLETE — no real request was dispatched.** The frozen candidate and source
checks pass, but the current process environment does not configure
`AGENT_LLM_API_KEY`, the variable required by the frozen live channel. This is a
local execution prerequisite failure, not a model correctness failure or evidence
that the supplier account/model is unavailable.

The user explicitly required stopping when zero-cost preflight fails. No credential
file was opened, no value was printed, no configuration or code was changed to
continue, and no unauthenticated request was attempted. The live entry was never
invoked; no paid admission receipt or single-use claim was created. This attempt
ends here and its authorization is not automatically reused.

## Frozen identity and preflight

- Worktree: `/home/dev/.codex/worktrees/tutor-v19-closeout-20261108`.
- Clean preflight HEAD: **`059b56561aaa1aef1d05770302f26861390f2e88`**.
- Actual live execution SHA: **NOT_RUN**, because no live invocation occurred.
- Frozen runtime code commit: `ae222cc76ec41aed78072713a9371eaff6000b2e`.
- Identity: `p8-tutor-selected-v19-development`.
- Manifest: `eval/tutor-selection-v19-v1/candidate.json`, SHA-256
  `16a094317ba06b3c1932280c7dbb15a07d47200dc74ed8e08e25465e10549ae9`.
- Original three-turn packet SHA-256:
  `ade24dceaf2bf50421b88373b68ebb65ba776c0d83754cab350fc06f558ba60e`.
- All18 candidate and22 parent-manifest entries match. All18 candidate blobs also
  match the frozen code commit. The default verify-only CLI exits0. The historical
  `ready_for_live=false` return is documentary boilerplate; it does not revoke the
  user's current authorization. The actual blocking observation is the missing
  runtime injection above.

The code retains3 ordinary decisions plus1 shared finish correction per turn,
12 requests/run,4096 output tokens/request, concurrency1, transport retries0,
body4096/evaluation1024 complete Unicode code points, and US$0.30 local reserved
plus settled liability. Format/span errors use one journaled allowance, never two.
No reviewer or embedding route is requested by this entry. No reference or scoring
material was injected into a product prompt; no product request was created.

The frozen source fences and default verifier were checked read-only. Database
startup/admission, provider authentication/access and live execution were **NOT_RUN**
after the prerequisite failure. Previous Mock passes are not new live validation.

## Official documentation review

The [official pricing page](https://api-docs.deepseek.com/quick_start/pricing/)
and [Chat API documentation](https://api-docs.deepseek.com/api/create-chat-completion/)
were rechecked on2026-11-08 before the stop. Exact requested API ID remains
`deepseek-flash`, with published moving backend DeepSeek-V4.1-Flash-1017. Published
peak input/output rates US$0.30/US$1.20 per million match the conservative frozen
ledger rates300/1200 nano-USD/token. At the wire/output caps the12-call theoretical
reservation remains US$0.294912, below US$0.30. Non-thinking required-tools mode and
4096 output tokens are documented configurations. Provider compliance with the
sent `parallel_tool_calls=false` is not established by current documentation.
No model-list, balance, account, embedding or reviewer API was called.

## Scheduled positions and quality

| Frozen position | Execution | Correctness / citation support | Answer / feedback code points |
|---|---|---|---|
| `v18-loop-teaching-smoke:1` | SKIPPED: preflight blocked | NOT_RUN / NOT_RUN | N/A / N/A |
| `v18-loop-teaching-smoke:2` | SKIPPED: preflight blocked | NOT_RUN / NOT_RUN | N/A / N/A |
| `v18-loop-teaching-smoke:3` | SKIPPED: preflight blocked | NOT_RUN / NOT_RUN | N/A / N/A |

Scheduled3; completed0; failed turns0; skipped3; missing scheduled records0.
There is1 **preflight failure**, counted separately from semantic/model failures.
No explanation, commented code, necessary point, citation support, feedback or
Socratic output was generated for review. A03 remains untested in a real v19
response; genuine source attribution must not be mistaken for correct semantics.
Codex performed same-author code/source preflight, **not independent human blind
review**. There is no real output to grade and no quality pass denominator.

## Requests, usage, ledger and retention

Real model requests0; embedding0; reviewer0; live CLI invocations0. Token/cache
usage is **NOT_OBSERVED_NO_REQUESTS**, not a zero-token model answer. No request or
response entity body exists because nothing was sent. No run ledger was created;
local reservations, settlements and outstanding request liability are all0.
The rate-based estimate for this attempt is **US$0**. Supplier actual debit is
**UNKNOWN / not queried**; no external invoice or account claim is made.

Private evidence: `.data/tutor-v19-live-20261108-preflight/` contains
`preflight.json`, `pricing.json`, `outcomes.json`, `results.json` and `events.jsonl`.
These are preflight records, not reconstructed/raw model responses. `RESULTS.json`
contains the derived/public record; `EVIDENCE_MANIFEST.json` indexes private hashes.
No credential file is included. The delivery commit containing this report adds
only these new records; resolve its SHA with `git log -1 --format=%H -- eval/tutor-v19-smoke-v1/REPORT.md`.

No temporary service/container/database was started, so no service cleanup was
needed. Original services, old worktree/branch, product code/defaults, frozen assets,
historical FAIL, CI and deployment remain untouched. No push/PR/merge occurred.

To unblock a future separately authorized attempt, provide the required runtime
variable via a controlled launch environment without disclosing its value in chat.
This phase does not search credential locations, change configuration, re-run, refill
positions or expand to16. **NOT_RUN:** real task quality, cost optimization,
independent human agreement, SQL holdout, expansion and learning effects. Stop and
wait for the next decision.
