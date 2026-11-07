# v12 diagnosis, opt-in v13 fix and stopped fresh-data preflight

**STOPPED AT NO-COST PREFLIGHT; real validation NOT_RUN.** The requested real trial
was not executed because the final corrected-reference bundle failed test
collection. The user explicitly required stopping before spending when regression
did not pass. This stage sent **0 real model / 0 embedding / 0 reviewer requests**,
used **USD 0**, and did not read a credential or create a live sender/ledger.
The stage's paid authorization does not carry forward.

Started clean at `837915cc49837b0f2e5fb003ab21adc5f7c53567` in the requested worktree
and branch. The implemented, frozen v13 candidate and first regression bundle
were committed as **`b1781987f7b15315e36f253f58c84903899ec6a5`**. That commit preserves
the exact runtime/entry/data/test bytes used by the 273-pass check; its test run
occurred just before the commit. The later additive locator-bundle test failed
in the worktree additions retained in this delivery. **There is no actual
real-execution SHA: NOT_RUN.**

## Diagnosis and scoring correction

[CAUSE_REPORT.md](CAUSE_REPORT.md) and private `cause-audit.json` inspect the one
incorrect, two uncertain v12 answers and all fifteen originally unsupported
assertions against exact final request bodies and original source. They separate
retrieval absence, input-context presence, output claims, attachment and scoring.

- The negative-index question and its following output were split at a `Solution`
  heading. The output-only passage was not retrieved on the actual query, while
  the question window was observed. The answer then made an unjustified
  whole-unit absence assertion. The structural split and false scope statement
  are proven; an internal model-attention explanation is not.
- The functions answer already had the required source passages, but added an
  unsupported “not an argument list” contrast. The metadata follow-up already
  had relevant metadata/table context and actual clarification, but left the
  missing encoding generic. Its rejected draft was already generic, so there is
  no demonstrated repair-induced deletion. Both original uncertain labels remain.
- Original citation gaps include two local excerpt/claim mismatches and uncited
  explanations/applications. Existing ID/authority validation does not establish
  semantic support; it did not rebind citations to wrong canonical text.
- One of the fifteen gaps was a duplicated paraphrase: markers:5 c5 repeats its
  already cited uncommon/type-risk claim c4. The additive correction is **59/73**
  supported requiring assertions, **61/73** citation presence and **4/12** fully
  supported expected answers, versus original 59/74, 61/74 and 3/12. Pair support
  59/62, full correctness **13/16** (one incorrect/two uncertain), conditional
  correctness **13/16**, and the **FAIL** decision are unchanged. Original reports
  and raw scores were not overwritten.

No root cause is asserted for hidden generation decisions. There is no evidence
that fixing the window alone resolves missing citations or under-specification.
The prospective prompt effects remain unmeasured in a real model.

## Minimal implemented intervention

New explicit identity: **`p8-tutor-claim-grounding-v13-development`**, manifest
SHA-256 **`70b4f27471a61fb6db64e1a8318b2e4540b2d1428614f5e29f3a6166f4dd43a7`**.
Runtime: `lecturelens_real_eval.tutor.claim_grounding_runtime:ClaimGroundingTutorRuntime`.
The identity is unregistered as a product default; v12 and earlier manifests
remain compatible and hash-verifiable.

The source-only authority coalesces a short question and immediately following
Solution inside the existing 1,000-character grouping bound, retaining original
member text/IDs/locations and a new context identity. On the actual old query,
the previously missed explicit negative-index output now reaches the context.
Foreign sources, ordinary headings, oversized groups and out-of-order boundaries
remain separated. Oversized indivisible source blocks keep fail-closed runtime
limits.

A single general system instruction requires checking all requested parts and
clarifications, distinguishing retrieved coverage from whole-unit coverage,
checking derivation premises and attaching supporting observed citations to all
factual results, explanations, applications and optional additions. It contains
no reference answers, task-specific wording or scoring thresholds. It does not
reduce citation requirements or ask the model to remove claims to improve a
metric. Updated request bytes are reserved, including prepaid format repairs.

No extra tool, semantic reviewer, automatic citation filler, repair opportunity,
request retry or budget expansion was added. Existing v12 stop/skip/accounting
functions are AST-identical in the first entry. Product default, CI, Java and
business data were untouched. The runtime is **implemented / mechanism-tested /
real quality unvalidated**, not released.

## No-cost checks and the stopping condition

| Check | Observed result | Meaning |
| --- | --- | --- |
| Configured foundational check | **10 passed**, no skip, 11.044 s | Actual missed-source query, source/member fidelity/boundaries, PG request budgets, full old response replay |
| Frozen first-bundle regression | **273 passed, 0 failed, 0 skipped**, 146.263 s | 18 new grounding/entry tests + 46 parent-entry + 42 recovery + 20 frozen-data + 147 Tutor/citation mechanism tests |
| v12 retained-response control | **42 exact request bodies / 16 unchanged answers**, same ledger | Reconstructed parsed response envelopes and metadata, not unavailable original raw HTTP bytes |
| Normal new Mock batch | **16 complete / 0 fail / 0 skip / 0 missing**, 32 sends | Mechanics only; no semantic quality or real costs |
| Local repeated-format Mock fault | **12 complete / 1 fail / 3 skipped / 0 missing**, 27 sends | Dependent skip and independent-topic session closure; other sessions continue |
| Global auth/usage/fabricated-ID/call/money faults | Expected stop/missing cases passed | No retry, reviewer 0, PG/JSONL events checked |
| Unsupported-valid-ID Mock fixture | Sixteen unsupported answers retained | Deliberately semantically bad; existence validation is not entailment |
| Corrected-reference final check | **Exit 2, one collection error, no tests executed** | `pytest` missing from new test imports; **stop gate triggered** |

All execution checks used a separate dedicated PostgreSQL and per-test schemas,
with the existing socket fence and stripped provider/proxy environment. Database
checks were not skipped. libpq is outside the Python socket counters; actual
PG-backed tests and mirrored records establish database checks, not a host-wide
network audit. One dependency deprecation warning in the 273-test run
is unrelated to this change. Exact supervisor logs, XML and network-fence terminal
records are retained. These results do not demonstrate model intelligence.

Early setup failures are preserved: a generic new `run.py` shadowed an old module
and was renamed `trial_run.py`; the socket launcher stripped the test DSN, so the
synthetic DSN was configured inside the guarded test process. The configured and
273-test checks then passed. Local lint initially used the wrong configuration;
Agent-service-configured lint passed on the frozen v13 implementation. Unmodified
upstream Markdown has trailing blank lines; source bytes were retained rather
than normalized to satisfy a whitespace check.

### New-sample authoring error and final failed check

The first fresh-data freeze incorrectly copied reference line numbers from web
presentation instead of the saved original spreadsheet Markdown. The later
pre-live source inspection caught the mismatch. For example, the Input Message /
Error Alert text is at original lines **71–77**, and the conditional-formatting
solution is at **170**, not the earlier displayed offsets. Therefore the first
bundle's claimed reference-location review was wrong even though its mechanical
checks passed. This was an assistant authoring error.

The first assets and hashes remain unchanged and are marked invalid for paid use
in [PREFLIGHT_INVALIDATION.md](PREFLIGHT_INVALIDATION.md). An additive
[tutor-v13-grounding-v2](../tutor-v13-grounding-v2/README.md) bundle records corrected
locations and matching quotes while leaving task text, reference points,
thresholds, candidate/runtime, source bytes and protocol unchanged. No real
candidate result existed, and no task was selected or removed in response to
quality. The final new test, however, used `pytest.mark.parametrize` without an
import; lint also identified that problem. This was another assistant mistake.
The final check failed at collection and verified none of that bundle's cases.

**The paid gate is not passed.** The earlier 273 successes do not substitute for
this later failed requirement. The failing bundle/test/hashes are retained;
there is no additional import fix, rerun, asset replacement or paid trial after
that terminal failure. Neither bundle is ready for live use. This stage is
incomplete with respect to the requested fresh real validation.

## Intended new sources and unchanged planned assessment

Both complete new source episodes use the already pinned repository revisions
of the same two development courses, with original licenses and attribution:

| Course / new episode | Pinned source revision | Source SHA-256 |
| --- | --- | --- |
| Python, `episodes/04-lists.md` | `eb18f246aee338b2a6169ba18d8c5ced7cf89f53` | `9f7cf80a805db45a25e89510153c5d1c6885e88c68d18fa6ce188fed08c7de41` |
| Ecology spreadsheets, `episodes/04-quality-control.md` | `78a54d7a7adcc961e83f463ba5392232e035cc6c` | `99ea134a3b98db2b59084fc05c6a0385f9d66257a708cf17d984c6af8f2b2dce` |

The 16 planned positions form four new sessions: shared/copy/nested lists;
non-continuous slicing and list overloading; validation bounds/alert/list policy;
and raw preservation, row-safe sorting and conditional formatting. They include
12 answerable tasks and four source-insufficient requests, ten contextual
followups, three critical indexing tasks and two clarifications. These are new
units/tasks, not rewrites of the old oxygen/array-statistics/null-table tasks.
Generic grounding, clarification and refusal skills necessarily overlap. No SQL
holdout, production, real student data, hand-acceptance account or external linked
workbook/image was used. Known public courses do not establish unseen-course
generalization.

Planned gate: all16 complete/reviewed; ≥14/16 full correct, ≥7/8 each course;
critical3/3, clean refusals4/4, clarifications2/2, context≥9/10, pair support≥95%,
requiring-claim coverage≥90%, fully supported answer turns≥10/12. These thresholds
were not changed after seeing candidate outputs. The first plan hash is
`84936102b448d237b016adb83339faf27d4c678193a17d4bd02be478cc16fd17`; its freeze hash is
`381beff7a312471e204e4e7b0622aea518fdf12bdd51b5ac442d7b03e9b32211`.
They identify the preserved invalid first bundle, not an executable approval.

## Real-result and cost census

| Quantity | This stage |
| --- | --- |
| Planned positions | 16 |
| Real attempted / completed / failed turns / dependency skips | **0 / 0 / 0 / 0** |
| Unexecuted positions | **16, NOT_RUN before dispatch** |
| Scorable / semantically scored real answers | **0 / 0** |
| Complete-correct scheduled / conditional quality | **NOT_RUN / NOT_RUN**; no fabricated zero-quality score |
| Critical / citation / refusal / context quality | **NOT_RUN** |
| Real requests including failures/repairs/retries | **0** |
| Real input / output / cache hit / cache miss tokens | **0 / 0 / 0 / 0**, no request made |
| Rate-calculated cost / local live ledger spend | **USD 0 / USD 0**, no live ledger created |
| User phase upper limit / existing lower envelope | USD 10 / USD 0.70 and 80 dispatches; no limit widened |
| Real model/response/request IDs, supplier invoice | **NOT_RUN**, not invented or queried |

The sixteen unexecuted positions are not runtime failures or dependency skips:
startup never occurred. They retain `NOT_RUN_PREFLIGHT_FAILED` in the private
planned-position census. There is one failed preflight collection record, outside
the turn denominator. Different-sample before/after quality, real cost change and
whether v13 meets the gate remain **NOT_RUN**; no old successful answers are
spliced into a new batch. No claim of improvement or readiness for expansion is
made. A public official pricing page was viewed without credentials; a compatible
live pricing observation/sender was never instantiated because the no-cost gate
failed first. No actual account debit/balance or immutable model version was
queried.

## Evidence, cleanup and remaining blockers

Private root:
`/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens/.data/tutor-v13-stage-20261107/`.

- `cause-audit.json`, `v12-score-correction.json`, `analyze.py`: original claims,
  exact request/source trace and additive score correction.
- `checks/`, `foundation-configured-evidence/`, `frozen-evidence/`,
  `frozen-parent-evidence/`, `frozen-recovery-evidence/`, pytest/XML and
  `network-*`: passed, failed and setup runs, Mock events/requests and replay.
- `checks/v13-reference-bundle-final.{json,log}`, `locators.xml`: final blocking
  exit-2 record and collection traceback.
- `service-preflight.json`, `closure-audit.json`, `cleanup.json`,
  `planned-position-census.json`, `artifact-manifest.json`: isolated resources,
  history preservation, zero live calls, planned omissions and retained evidence.

All four historical raw manifests remain unchanged: **62 + 592 + 1,571 + 72 files**.
The original v11 **34 events / seven turns / two sessions**, v12 **84 events /
16 turns / four sessions**, and 2,011 original allowed tracked hashes are unchanged.
Private evidence manifest: **828 files**, SHA-256
`4e9417e7f10c3e9716acb826d378625127bc346d592c4aa9c2e07cd0cfb1ed46`.
No unknown uncommitted work or other workspace was touched. The dedicated pinned
PG is stopped **exited 0**, port 25841 closed, its volume retained, and all **23**
original running containers remain running. No other service stack was started.
No push, PR, merge, deployment, rented server or follow-on schedule exists.

Remaining blockers are the failed final preflight/import and acceptance of a
correct original-source locator bundle before any future real execution. The
behavioral quality hypotheses are also unverified; no further fix or paid run
continues under this stage. **NOT_RUN:** new real-model quality and cost change,
independent human agreement/kappa, SQL holdout, expansion/60/300, learning effects,
unseen-course generalization, live reviewer/embedding and supplier billing/model
version verification.
