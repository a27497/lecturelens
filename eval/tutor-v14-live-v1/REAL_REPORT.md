# v14 frozen fresh16: one authorized real trial

**FAIL.** Ten positions completed, two failed after their sole format repair,
four were dependency-skipped, and none are missing. Complete correctness is
**9/16 scheduled (56.25%)**, or **9/10 completed answers (90%)**. The trial fails
the frozen all16-complete requirement and several other requirements below.
It does **not** qualify for expansion. No candidate repair, selective retry,
replacement sample or second real batch follows this result.

This is **Codex nonblind original-source review, not independent human review**.
All16 outcome positions were reviewed;10 published answers are scorable/scored:
nine complete-correct, one incomplete, zero uncertain. Failed drafts earn no
semantic success credit. The raw execution summary retains its pre-review
`quality_status=NOT_RUN`; this additive report and separate annotations supply
the subsequent assessment without rewriting raw or historical results.

## Execution identity and frozen inputs

Started clean on `codex/tutor-scale-preparation` in the explicitly requested
worktree. **Actual execution SHA: `81020d1abd7c89a995bf9eba153302af7481c71b`.**
This delivery adds only this report and its non-sensitive summary. Tutor code,
identity, prompts, defaults, CI, original files, references and gates are unchanged.

| Binding | Value |
| --- | --- |
| Explicit identity | `p8-tutor-draft-repair-v14-development` |
| Candidate SHA-256 | `180929dee65677f105b1d9c85705394b28b8dc90a0edef2e99abc140821420b3` |
| Frozen bundle | `eval/tutor-v14-fresh-v1/` |
| `freeze-lock.json` SHA-256 | `ba3d1b14dd410e770b2cdfd062e3c7042d93d70a32c27b61d871472aecb390a0` |
| `run-plan.json` SHA-256 | `f28b9bae8fd653ed09922ec5a451a7b629e98b5c6c32dec45c6077027dfb2576` |
| `grading-rules.json` SHA-256 | `6c08abb8ee86c647e0b4d1b1719b0867d92312af623f4c2d9e6d8665ea2942e8` |
| Stop protocol | `v12-session-isolated-live-v1` |
| Protocol JSON SHA-256 | `926f79b8f0c873b18ffab7d8efdaad9668f0ba605040fdba2070df126d4104e5` |
| Independent run label / PG run ID | `v14-frozen16-once` / `fresh-v14-v14-frozen16-once` |
| Dispatch interval, UTC | 2026-11-07 15:37:42–15:38:46 |
| Requested / returned API model | `deepseek-flash` / `deepseek-flash` on all32 calls |
| Immutable response version | UNKNOWN; the API name is a moving alias |
| System fingerprint | `bc19ba97cbe016479903222bb1578db6` on all32; not an immutable version guarantee |
| Settings | temperature0, thinking disabled, output1,200 tokens; reviewer off; concurrency1; transport/SDK/application retries0 |
| Runtime bounds | text1,600/evaluation500 characters; four distinct citations; two searches; one format/one mode repair;64,000 turn/640,000 session proxy;60 calls/session |
| Batch ceilings |80 real requests; USD0.70 local reserved-plus-settled |

The existing four complete sessions and16 questions were used unchanged. Both
courses are public development data: Python **05-loop**, pinned revision
`eb18f246aee338b2a6169ba18d8c5ced7cf89f53`, and ecology spreadsheets
**05-exporting-data**, revision `78a54d7a7adcc961e83f463ba5392232e035cc6c`.
The complete source files contain435 and149 lines respectively. Python bytes
still hash to `59ad81e33ec8881f3a8bafb8f220ec5b9bea8af6e9caee7fbdefffaa703ffc53`;
spreadsheets to `bee635840b85dfa2a78eaaa2bd4dbd0b03f4d0ba51beb3437d4afd58a5814b3e`.
No new questions were authored or old answers spliced into this run. The earlier
zero-request source-formatting rejection and recovery evidence remain intact.

## Frozen gate and denominators

Every frozen condition must pass. Ratios concerning published assertions do not
remove failed/skipped tasks from scheduled correctness or full-answer coverage.

| Requirement | This trial | Result |
| --- | --- | --- |
| Complete16/16, failures/skips/missing0 |10/16;2 failures;4 skips;0 missing | FAIL |
| Review16/16 |16/16 outcome reviews;10/10 scorable answers scored | PASS |
| Complete-correct at least14/16 |9/16 | FAIL |
| Python at least7/8 |8/8 | PASS |
| Spreadsheets at least7/8 |1/8 | FAIL |
| Critical range/enumerate tasks3/3 |3/3 | PASS |
| Clean insufficient-evidence refusals4/4 |2/4 scheduled;2/2 observed | FAIL |
| Clarifications2/2 |1/2 scheduled;1/1 observed | FAIL |
| Consistent context tasks at least9/10 |6/10 scheduled;6/6 observed | FAIL |
| Explicit claim–citation support at least95% |36/36,100% | PASS |
| Requiring-claim support coverage at least90% |42/42,100% under frozen derivation rule | PASS |
| Fully supported, complete expected answers at least10/12 |7/12,58.33% | FAIL |

Expected16 = attempted12 + unexecuted4. Attempted12 = completed10 + failed2.
Unexecuted4 = skipped4 + missing0. Unknown attempts0. Expected answerable12 and
insufficient4 remain unchanged. There are eight substantive published answers
and two published refusals; seven substantive answers satisfy complete-reference
coverage. Context consistency is judged separately from reference completeness:
lineends2 is context-consistent but incomplete.

## Review of every position

Line references below address the complete original Markdown files under the
frozen bundle's `materials/`, not video timestamps or PDF pages. Exact references,
answer spans, claim annotations, observed evidence/member IDs and source quotes
are retained privately in `codex-source-review.json`.

| Position | Status / complete correctness | Original-source finding |
| --- | --- | --- |
| python-counter1 | completed / correct | Initial0; Curie1, Darwin2, Turing3; exact final line; once-only unindented print. Python134–154,189–217. |
| python-counter2 | completed / correct | Four outputs exact; Turing persists and Rosalind is not restored in this example. Python219–235; indentation151–154. |
| python-counter3 | completed / correct | All three ranges exact; exclusive stop4 includes3; correct `range(1,4)` loop. Python255–286. |
| python-counter4 | completed / correct refusal | Complete episode supplies no C storage/byte-allocation uniqueness theorem. |
| python-polynomial1 | completed / correct | Index/value pairs(0,2),(1,4),(2,3), coefficient order and result97; cited bounded computation. Python379–419. |
| python-polynomial2 | completed / correct clarification | Corrects one-based confusion; exponent0/contribution2; terms20/75 and total97. Python379–419. |
| python-polynomial3 | completed / correct | Exact initialization/loop, distinct index/coefficient roles, trace2→22→97 and final result. Python397–419. |
| python-polynomial4 | completed / correct refusal | No all-rounding-mode IEEE754 stability theorem, bound or proof in the complete episode. |
| sheets-portability1 | failed / no published answer | Four reasons, other-format caveat, TSV/CSV, portability and Excel reopening requested; initial and repair exceed size bound. Spreadsheets20–62. |
| sheets-portability2 | skipped / no answer | Dependency root portability1; only-CSV/Excel-reopening clarification untested. Spreadsheets46–62. |
| sheets-portability3 | skipped / no answer | Blocked by portability2, root portability1; Save-as procedure untested. Spreadsheets57–62. |
| sheets-portability4 | skipped / no refusal | Blocked by portability1/3; requested date-formula/edge-case refusal unobserved. Complete episode has warning39–44 but no requested algorithm. |
| sheets-lineends1 | completed / correct | LF/CRLF, non-CR-parser condition, attributed integer example, and explicit non-universality. Spreadsheets68–94. |
| sheets-lineends2 | completed / **incomplete** | Correctly rejects only-Windows and universal failure; **omits the frozen reference's Excel-reopening/parsing counterexample**, spreadsheets76–78. |
| sheets-lineends3 | failed / no published answer | Three remedies, Git files/pattern, R alternative and all caveats; both drafts exceed size bound. Spreadsheets96–132. |
| sheets-lineends4 | skipped / no refusal | Blocked by lineends3; complete episode supplies no RFC4180 ABNF/quote-parser state machine. |

The incomplete answer says that the parser condition is conditional and rejects
its converse. Its assertions are supported, but it never mentions Excel reopening
and parsing its export. The unchanged second reference point explicitly includes
that counterexample. Under the frozen every-required-point rule, source-correct
assertions alone do not make the answer fully correct. An initial private review
draft overlooked this omission and counted10 correct. That draft is preserved;
`review-bookkeeping.json` records the correction to9. No historical score,
reference or threshold was edited.

The spreadsheet source contains dated software guidance. Per the **pre-result
execution sheet**, the `2\\r` example is scored as attributed supplied-unit guidance
under the stated parser condition. It is not evidence about modern R/Python
integer conversion or every importer. No current interoperability experiment
was performed. This source limitation does not authorize a post-result rubric
change.

## Citation support, coverage and exclusive scope

The completed-answer inventory has47 semantic claim units, including compound
named worked examples/lists judged conjunctively. Forty-two require positive
source support; five are negative-scope/refusal statements, separately truth-
reviewed against the complete units. Repeated semantic claims are deduplicated
within each answer; distinct derivations and their premises remain separate.
All optional factual additions are included.

There are **36 supported/36 explicit substantive claim–citation pairs**, including
one explicit negative-scope pair; unsupported0, uncertain0. Direct citation
presence and directly supported requiring claims are **35/42 (83.33%)**. Seven
expressly signaled step-by-step/evaluated/iteration/“So” derivations have all
premises locally cited: counter1's update trace and final output; counter3's
stop comparison; polynomial1's evaluation; polynomial2's constant and other-term
calculations; polynomial3's accumulator trace. Applying the unchanged bounded-
derivation rule yields **42/42 supported requiring claims**. No direct inline pair
was invented for those seven conclusions. Generic nearby citations are not
inherited. Direct-only sensitivity is **2/12** fully supported complete expected
answers, versus **7/12** under the frozen rule. The incomplete lineends2 answer
does not qualify in either full-answer numerator.

These assertion ratios cover published answers only. They are not16-position
success rates. An omitted required point is caught by correctness/full-answer
coverage even though no corresponding assertion exists in the claim denominator.
Failed drafts, skipped tasks and unavailable refusals cannot improve that12-task
denominator.

No unsupported exclusive addition was found in10 published answers. Counter1's
only-indented-body explanation follows the actual code; counter3's never4/only1,2
follows the cited exclusive stop. Lineends1/2 preserve the parser condition and
reject the user's platform/universal extrapolation. Both conditional-scope probes
were published; only1/2 is complete-correct because of lineends2's omission.
The designated only-CSV clarification was skipped, and the narrow some-only-
Windows checklist failed publication. The latter's rejected drafts preserve
“some” and do not generalize to all R packages; **they earn no success credit**.
This is limited observed scope preservation, not proof that exclusivity defects
are generally resolved.

Canonical passages sometimes omit figure or delimiter-only gaps inside their
line envelopes. Post-run audit verifies the exact existing double-newline join
of canonical member texts, every member locator/hash, and unchanged repair
mapping. An envelope must not be misrepresented as a contiguous original quote.
No supporting claim here depends on omitted image contents.

## Two local failures and observed continuation

| Failed position | Initial → sole repair text chars | Repair excess over1,600 | Turn proxy /64,000 | Consequence |
| --- | --- | --- | --- | --- |
| portability1 |1,982→1,799 |199 |39,463 | Skip portability2/3/4; continue independent lineends session |
| lineends3 |1,818→1,633 |33 |48,534 | Skip lineends4 |

Both initial violations are text size only: no excess/remove citation IDs, no
evaluation-size violation. Each receives exactly one format repair with explicit
target1,200/hard1,600 characters, the **exact original rejected draft**, and its
unchanged kept evidence mapping. Repair requests are wire25 and32. Their local
context reservations,17,133 and18,880 proxy units, succeed. Neither repair meets
the hard text limit: **real repair success0/2**. Repaired drafts retain nine and
ten inline citation occurrences respectively; their characters count toward the
existing limit. Neither draft was truncated or published.

The direct observed failure is insufficient compression in generation/repair,
followed by correct format validation and `TUTOR_FINISH_FORMAT_INVALID`. It is
not a total-money exhaustion, lost rejected draft or refused repair reservation.
Why this moving model fails the explicit compression request remains unverified;
this trial cannot establish a further implementation root cause or fix. The
drafts appear to retain requested points and qualifiers but are **failed outputs**.

The exact frozen local-failure contract operated: each failed session closed,
dependency skips retained blocked-by/root-failure IDs, and the independent
lineends session began at wire26 with a distinct ID and empty history, summary
and initial evidence. All four session starts were isolated. No global stop,
authentication failure, unknown usage, protocol error or cap exhaustion occurred.
The supervised command's exit1 records incomplete execution; it is not silently
converted into mechanical completion.

## Requests, usage and costs

**32/80 real dispatches**, all HTTP200 with known usage;32 settled calls,
64 reserve/settle ledger events, pending0, blockednull. Of32 executed decisions,
18 search and14 finish include the two repairs. There were35 parsed proposals:
21 searches/14 finishes, including **three ignored parallel search proposals**;
those were not extra dispatches or tool executions. Transport/SDK/application
retries0, embedding calls0, reviewer calls0. No request followed the one trial.

| Supplier-returned usage | Tokens |
| --- | ---: |
| Input |122,392 |
| Cache-hit input, included in input |34,560 |
| Cache-miss input, included in input |87,832 |
| Output |7,862 |
| Input + output |130,254 |

The [official DeepSeek pricing page](https://api-docs.deepseek.com/quick_start/pricing/)
was checked on2026-11-07 before dispatch. All requests occurred during Saturday
off-peak pricing. Per million tokens, observed USD rates are cache-miss input0.15,
cache-hit input0.003, output0.60; conservative peak/cache-miss rates input0.30 /
output1.20 remain compatible with the existing reservation mechanism. The saved
page SHA-256 is `af6679690eb9a7838c47727bfc5ffdc4ac91c4445a0c1219741ffe00c076ece5`.
Its documented model version is not an immutable response identifier.

- **Rate-calculated, cache-aware off-peak estimate: USD0.01799568** =
  `(87,832×0.15 +34,560×0.003 +7,862×0.60) /1,000,000`.
- **Local ledger settlement: USD0.046152** =
  `(122,392×0.30 +7,862×1.20) /1,000,000`. This deliberately uses conservative
  no-cache peak prices; it is not the cache-aware estimate or supplier invoice.
- **Maximum local reserved-plus-settled exposure: USD0.0505362**, below USD0.70.
  Every prefix was reconciled. Each pre-send reserve uses exact wire UTF-8
  bytes×300 +1,200 maximum output tokens×1,200 nano-USD. Final pending0.
- **Supplier actual debit/invoice/hard-cap enforcement: UNKNOWN, not queried.**
  The accepted local cap does not enforce the supplier's bill. Unused allowance
  does not authorize a further request or batch.

All32 response IDs, local request IDs and ledger call IDs are retained and unique.
Supplier request-header ID is absent/UNKNOWN on32/32. Returned model and cache
counts are known on32/32; immutable version remains UNKNOWN. A fingerprint or
pricing-page version does not remove the moving-alias limitation.

## Preflight, evidence and cleanup

The unchanged entry verifies the registered identity, full freeze/source/reference
chain and original219-pass evidence. Its recovery249-pass record and all2,356
artifact hashes were also rechecked. Necessary fresh-entry/asset regressions
were rerun against the isolated PG under the no-egress/no-credential/no-real-
transport fence: **30 passed, zero failed/errors/skipped**, pytest29.77s,
supervisor32.502s, exit0. No paid probe preceded the real trial.

```sh
python3 scripts/dev/run_check.py --name v14-live-preflight --timeout 1200 --output .data/tutor-v14-live-20261107/checks -- agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-v14-live-20261107/network-preflight .data/tutor-v14-live-20261107/preflight.py
python3 scripts/dev/run_check.py --name v14-real-once --timeout 1200 --output .data/tutor-v14-live-20261107/checks -- agent-service/.venv/bin/python .data/tutor-v14-live-20261107/execute_once.py
```

The second command ran once, through the unchanged frozen `run_fresh.py` entry;
supervisor exit1,65.619s. The one-use sender consumes the provisioned evaluation
credential internally; no credential value/header was inspected, logged or
committed. Its single-use lock and start/end records prevent accidental replay.

Private evidence root: **`.data/tutor-v14-live-20261107/`**. The exact run is
**`v14-frozen16-once/`** inside that root. Retained artifacts include:

- `config.json`, expected/attempted/partial/final turn inventories and immutable
  raw summary; all contexts, retrieved/selected evidence, checkpoint observations,
  rejected/repair proposals, published answers and failure/skip reasons;
- exact32 wire request bodies, allowlisted response metadata, parsed proposals
  including ignored calls, usage/cache, correlation IDs, wire/call/ledger JSONL;
- `postgres-run-snapshot.json`, restricted to this synthetic run's12 turns/four
  sessions/64 events; PG and file outcomes/usage/checkpoints reconcile exactly;
- `reconciliation.json`, `post-run-audit.json`, `failure-review.json`,
  `exclusivity-review.json`, `codex-source-review.json` and source-span annotations;
- official pricing HTML/observation, authorization, supervised commands, JUnit,
  isolated entry/Mock artifacts, cleanup and protected-before hashes.

Full raw HTTP response byte bodies are **not** retained; parsed proposals and
allowlisted telemetry are. Missing provider fields stay UNKNOWN. This is a
capture limitation, not evidence of an extra request. Initial offline annotation
anchor and audit-envelope assumption failures are preserved separately with
their corrected bookkeeping; neither changes runtime output or causes real calls.

Final manifest: **358 private files**, SHA-256
`2b9c39428d10473f4d088badfbae93b17ab4e973a8660c4521b0dafcbafb06cd`.
All32 protected source/frozen/runtime files remain unchanged. Historical recovery,
previous zero-request rejection and v13 evidence manifests verify2,356/17/487
files unchanged. Private/downloaded records remain outside Git.

Only the existing dedicated resource-bounded PG was started: loopback25841,
384MiB/0.5CPU, exact container
`lecturelens-tutor-scale-prep-20261107-postgres-1`. After export it stopped with
exit0; port25841 is closed, its volume retained, and the exact original23 running
containers remain running. No other workspace or service was changed.

## Comparison and remaining blockers

For descriptive context, the previous v13 batch completed12/16, failed1, skipped3,
with11/16 scheduled correctness and11/12 conditional correctness. This v14 trial
completed10/16, failed2, skipped4, with9/16 and9/10 respectively. **The tasks/units
and candidate differ; the session-isolation stop protocol is unchanged.** These
numbers are not a controlled before/after effect, a strict quality improvement,
or evidence of generalization. No successful historical answer is reused.

The remaining observed blockers are repeated overlength repair failure on
multi-part spreadsheet tasks and the missing required counterexample. High
published-assertion support does not compensate for lost complete conversations
or omitted requested evidence. Offline mechanism success did not establish real
repair effectiveness. This run provides neither a new fix nor justification for
expansion; any future work needs a separate scope/authorization and must preserve
this failed batch. **This one-batch authorization has ended.**

**NOT_RUN:** cost optimization, independent human agreement, SQL holdout,
expansion and learning effects. No deployment, push, PR, merge or product-default
change occurred.
