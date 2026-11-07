# Frozen v12 real-entry no-cost preflight

**Ready for a separately authorized full 16-position development rerun. No real
request was made.** The default entry prepares only; the real branch now exists
with explicit identity, source/configuration locks, new-batch spending gates,
unchanged bounded runtime/ledger protections and auditable failure propagation.
This task made **0 real model / 0 embedding / 0 reviewer calls**. It did not query
pricing, balance, account billing or model availability. All real post-fix quality
and cost changes remain **NOT_RUN**.

Started clean at `b78a39b256c156f996d4f1a3d43ae2751699fb82` in the requested
worktree/branch. **Actual final verification code:**
`982339cc4f871d14fe1d230e7e1538b917b363e0`.
Only the fixed-scope `eval/tutor-v12-rerun-v1/` directory was added. No generic
platform, shared runtime, product default, schema migration, CI, other workspace,
production/student data, SQL holdout, push/PR/merge/deployment or rented service
was introduced or modified.

## Frozen bindings

| Artifact | Identity / SHA-256 |
| --- | --- |
| Candidate | `p8-tutor-repair-context-v12-development` |
| Unchanged v12 candidate manifest | `4540369887eb2d84f79ee5351a8e1c0c82af859be8ff8d364ce7faf262a3afb2` |
| Runtime | `lecturelens_real_eval.tutor.repair_context_runtime:RepairContextTutorRuntime` |
| Protocol | `v12-session-isolated-live-v1` |
| Run plan | `6a684a138d9fe2a04ccbb51f9d3bdbab25b44b5465a21a0c1082bbbc33dad825` |
| Protocol JSON | `926f79b8f0c873b18ffab7d8efdaad9668f0ba605040fdba2070df126d4104e5` |
| Adapter lock, including targeted tests | `cdb50106d25f2b808d099080ccc33fc8ed21dd86d388369dc25697180f214e47` |
| Original batch plan | `4efdabb65a323155366184523757779a04b7ddfc7baf6717638590bdb91100ad` |
| Original grading rules | `0eb59ce214d5607205d1b3cb9b12090ea0ba00ef83455a01e4ff42e317e628ca` |

The plan additionally binds the original dataset/freeze/part-plan hashes. The
existing development-only loader verifies the two original source/license files,
question/reference locks and all 16 keys. Missing data, stale hashes, inconsistent
adapter identity or the old v11 Agent refuses before directory/DB/transport/key
lookup. There is no data selector, alternate model or fallback identity.
Candidate code and the old v11/v12 protocols/manifests/results are unchanged.

[The entry](rerun.py) uses the existing `TutorOnlyChannel`, decoded metadata
recorder, PG store/ledger, pricing validator and v12 runtime. One small channel
guard blocks decoded usage/cache anomalies immediately; waiting for the outer
turn to finish could otherwise permit a second request. It neither repairs nor
relabels an inconsistent response. The existing channel still owns send-time
usage/protocol validation, reservations and no-retry behavior.

## Execution contract

The [protocol](PROTOCOL.md) freezes the five exact local terminal codes from the
existing bounded runtime. Global accounting and channel/usage failures take
precedence. Auth/model/protocol/citation/authority failures, cancellation, unknown
errors or pending/blocked/divergent/unknown accounting stop all sessions. A missing
accounting field is unknown, not healthy. No global problem is classified merely
by a `TUTOR_` prefix as local.

After a local failure, preserve it and close that complete conversation. Subsequent
positions with failed/skipped prerequisites are `SKIPPED` with dependency/root
failure IDs; an independent topic in that same closed session is conservatively
`SKIPPED` with an explicit session-closure reason. Continue only later independent
sessions, with empty history/summary and new session/synthetic scope IDs. All share
one **new global ledger** and its remaining limits. This new allocation does not
pool or reuse the historical A/B allowances, ledgers or expired authorization.

A global stop leaves unattempted positions `MISSING` with a stop reason. Attempts
are recorded before execution; known attempted IDs survive an unavailable result
as UNKNOWN/failed-unresolved, not a fabricated answer. All 16 expected records are
written before dispatch. Failed records/checkpoints and channel/ledger traces
survive a stop; no automatic resume, resend, top-up or semantic rerun exists.

Concurrency remains **1**, requested model `deepseek-flash`, temperature 0, thinking
disabled, max output 1,200 tokens, reviewer off and all transport/SDK/application
transport retries **0**. Runtime 64,000 turn / 640,000 session byte-proxy bounds,
60 session calls, two searches and the existing one format/one mode repair are
unchanged. Actual returned model/version metadata is recorded; an immutable
backend version remains unknown for the moving alias.

## Targeted validation

At the actual verification commit, supervised final tests completed in **57.569 s**:
**108 passed, 0 skipped, 0 failed** — **46 new entry tests**, **42 unchanged v12
recovery tests**, **20 unchanged frozen-data tests**. A real dedicated PostgreSQL
instance and per-test schemas were used, not skipped DB checks or a memory-only
substitute. Ruff check/format passed using Agent service configuration. Shared
runtime code did not change, so the broader 122-test runtime suite already recorded
in the previous report was not unnecessarily repeated here.

| Scenario | Completed / failed / skipped / missing | Evidence |
| --- | --- | --- |
| Complete default Mock batch | **16 / 0 / 0 / 0**, 32 sends, reviewer 0 | Exact 16 keys/order, all request settings/context shapes, 64 mirrored PG/JSONL events |
| First-session repeated format failure | **11 / 1 / 4 / 0** | Three dependency skips plus one conservative session-closure skip; all three later sessions start empty |
| Auth 401 / model unavailable 404 / transport timeout / malformed protocol / missing usage | **0 / 1 / 0 / 15**, one send each, no retry | Preserved failed record, usage/reservation outcome, global stop |
| Inconsistent numeric usage metadata | **0 / 1 / 0 / 15**, one send | Immediate durable channel block before next decision |
| Fabricated citation | **0 / 1 / 0 / 15**, search then rejected finish | Canonical source validation blocks batch |
| One-call global cap | **0 / 1 / 0 / 15**, one send | Next reservation refused before wire send |
| Tiny explicit money envelope | **0 / 1 / 0 / 15**, zero sends | No reservation; ledger refuses before dispatch |
| Exact cap on final planned response | **16 / 0 / 0 / 0**, 32 sends | Mechanically complete, healthy accounting, no extra dispatch |
| Divergent ledger | **0 / 1 / 0 / 15**, one send | Corrupt JSONL retained; accounting null, no reset/repair/retry |
| v12 retained prefix plus synthetic repair at explicit Mock cap 18 | **7 / 0 / 0 / 9** | First 17 requests exact; nine unattempted positions remain missing at a deliberate Mock cap, not a quality result |
| Old v11 retained-response replay | Original **6 completed / 1 failed / 9 missing** | Original failure and six answers preserved by unchanged recovery tests |

For each normal/fault batch with consistent accounting, an independent test query
compares full PG event contents with JSONL and persisted turn status, answer,
counters and checkpoint with the captured records. Wire request SHA-256 matches
observer/call/reservation records. Model request data contains only the runtime's
learner/context/evidence/observation fields, not evaluation reference/rubric fields.
The deliberately divergent case is preserved as divergent, never forced to match.
Separate tests cover all five local codes, global precedence over a local-looking
error, unknown/cancelled/authority failures, invalid/missing config and input files,
new authorization/price gates, zero reviewer dispatch and wire-write failure before
transport. The inherited recovery tests cover exact turn/session boundaries,
one-shot exhaustion, prepaid restart, cancellation, unknown outcomes and full-union
source checks before projecting away a fifth source.

The positive live **preflight-only** unit test uses a synthetic pricing file and
blocked transport/DB hooks. It verifies gates, not today's official rates, a
credential, account balance or API access. There was no real live sender smoke test.
The Mock complete batch's expected-insufficiency fixture is a mechanics oracle;
its outcomes/usage/ledger values are not real quality, tokens or supplier charges.

Development evidence is retained: an initial check had 33 pass / 3 fail because
multiple test cases archived under the same exclusive filename. All execution
assertions preceding archive creation passed; archive names were made case-specific,
without weakening execution assertions or overwriting old results. A subsequent
44-test check and 107-test combination passed. Final review added a fail-closed
schema boundary for a missing `blocked` field; the existing ledger always supplies
that field, so no historical actual run is asserted affected. The final 108-test
run verifies that guard. These are no-cost check iterations, not new model trials.

## Seventh-turn replay and citation mapping

Complete original provider body bytes were not retained. Replay reconstructs
synthetic envelopes from retained parsed tool calls, dropped-call count and
allowlisted response/usage/cache metadata; unrecorded fields are not invented as
historical fact. The unchanged v11 failure replay remains intact.

In the new entry, the first **17 request bodies match exactly** and the first six
answers remain unchanged. The known rejected finish has five IDs and 1,601
characters. Its old 45,053 + 23,897 reservation still exceeds 64,000 in v11.
The unchanged v12 projects the repair evidence from 12 sources to the journal's
four kept IDs: **45,053 + 16,422 = 61,475**, with no larger budget or additional
repair chance. The synthetic eighteenth response only demonstrates execution.

Tests compare the final checkpoint's **exact 12 selected IDs** with the original
failed checkpoint, compare every projected source field against the same canonical
source ID/text and compare published citation objects against that same map.
There is no ID renumbering, text substitution or loss of the full authoritative
selection. The controller still re-READs all selected IDs, including a removed
fifth source, before repair; foreign/missing/deleted authority remains fatal.
This proves citation identity/existence mechanics, **not semantic claim support**.
The synthetic short answer can omit required metadata and is never graded as a
real task success. The earlier source-scope/exclusivity/citation-fidelity quality
blockers remain unmeasured after the fix.

## Fixed reporting and next authorization

Use the original rubric unchanged. Report verified complete correct **X/16** and
**X/C completed**, plus completed/failed-unresolved/skipped/missing and
scorable/reviewed/uncertain counts. Also report unknown-attempt subset and total
unexecuted = skipped + missing. The old batch's nine missing positions are not
retroactively converted into explicit skips. Its original **3/16** delivery and
**3/6** conditional correctness, citation support **18/21** and supported claim
coverage **18/25** over six completed answers remain unchanged.

Citation pair/claim ratios must state that their content inventory covers completed
published answers, including material optional/uncited assertions and uncertain
pairs. Expected-answer full supported coverage keeps all **12** scheduled answerable
positions (old result **1/12**); failed/skipped/missing/wrong-refusal outputs cannot
improve it. No labels/pairs produce null/NOT_RUN. Strict acceptance still requires
all 16 completed/reviewed and every original threshold; a new skip category cannot
make an incomplete trial pass.

The [real execution sheet](EXECUTION_SHEET.md) is now concrete but **unapproved**:
normal requests **32**, second-search path **48**, theoretical existing-repair max
**80**; new explicit total request and USD authorization is required. The unchanged
local tool ceiling is **USD 0.70**, not a grant or consumption target. The old USD 10
or unused allowance is not carried forward. The frozen peak/no-cache reservation
basis is documented, but current public pricing must be reviewed/retained again on
the actual UTC execution date and be compatible; otherwise the entry stops. The
local ledger is not a supplier invoice hard cap; actual billing/protection and
immutable model version remain unknown.

There is no remaining known code/Mock-preflight blocker. Before real execution,
obtain a new grant, review execution-day pricing/billing limitation and reverify
the dedicated DB and sender environment. API/model access, credentials and balance
have intentionally not been probed. Run **one full new 16-position trial with four
new sessions**, not a selected tail or a splice with old successful answers.
Candidate and failure protocol both changed versus v11, so completion differences
cannot all be attributed to answer quality. This is consumed development data,
not an independent fresh holdout.

## Evidence and cleanup

New raw root:
`/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens/.data/tutor-v12-entry-20261107/`.

`entry-audit.json`, `final-tests.xml`, `checks/entry-final.{json,log}`,
`pytest-final/`, `final-evidence/`, `inherited-final-recovery-evidence/`,
`network-final/`, `preflight.json` and `cleanup.json` retain the full checks and
per-case traces. Draft/development checks and the additional schema-boundary
review are preserved separately. `artifact-manifest.json` hashes private evidence;
[VERIFICATION.json](VERIFICATION.json) contains non-sensitive aggregate provenance.

Both prior raw manifests remain unchanged (**62 + 592 files**), as do the original
**34 PG events / two sessions / seven turns**, all 2,011 earlier allowed-file hashes
and every preexisting tracked file checked by Git. The v12 manifest and old frozen
validators still pass. No credential value was read/logged/committed. The socket
launcher stripped provider/proxy environment; final external-attempt counters are
zero. libpq is outside Python socket counters, so actual PG records/tests supply
database evidence, not a claimed host-wide packet audit.

The dedicated pinned PostgreSQL container (sole volume consumer, no dependencies,
loopback 25841, 0.5 CPU / 384 MiB) is restored to **exited 0**, port closed, volume
retained; all **23** preexisting running containers remain running. No other
service stack was started.

**NOT_RUN:** real v12 rerun/post-fix quality, real token/cost change, independent
human agreement/kappa, SQL holdout, expansion/300 turns, learning effects,
unseen-course generalization, live reviewer/embedding, actual API/access/billing
verification. No follow-on execution is scheduled; wait for new paid authorization.
