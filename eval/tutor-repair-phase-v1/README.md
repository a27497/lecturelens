# Zero-cost Tutor repair phase

Work starts from `7c913ecb2ccd3756c78d2126b90e63ee4221ccfd`. No historical
source, manifest, result, question or score is edited. All model, embedding and
reviewer calls remain zero. Product defaults and CI remain unchanged.

## Stage 1: obligations and bounded delivery

`contract-v2.json` is consumed-development regression material, not fresh holdout.
It retains all sixteen tasks, every reference point and every original threshold.
One explicit request is strengthened to name the already mandatory Excel
reopening/parsing example; no requirement is removed based on an observed answer.
The revision records the source-based rationale. Historical v14 remains FAIL.

The new opt-in v15 model contract has at most four answer blocks of 300 characters
and two evaluation blocks of 160 characters. Every block binds one full canonical
source ID (at most64 characters). Rendering adds a course-attribution header,
optional derivation label, separator and full canonical citation. All rendered
characters count toward the unchanged1600/500 limits. The browser/storage protocol
is unchanged. This is explicit grouping with local provenance, not a short-citation
map or silent removal of claim-level citation anchors. The inherited distinct-ID,
version, ownership and final publication checks still apply.

The v14 failures preserve nine/ten repeated markers and reach1799/1633 characters
after repair. Four source-bound blocks bound representation cost without asking
the model to emit/repeat nine/ten hashes. Related claims may share a block only
when that source supports them. Legal maximum block layouts with ASCII, Chinese,
emoji and newlines render within the original limits. Invalid/overlength blocks
get one durable prepaid format repair; another violation fails. No truncation,
extra paid retry, model-supplied private reference or final length relaxation is
introduced. Preserving necessary facts is still a semantic evaluation requirement;
Mock or manually authored block content cannot establish real generation success.

Stage1 targeted checks: `phase1-delivery` supervisor exit0, nine tests passed with
real disposable PostgreSQL and credential/HTTP/socket guards. Commands and JUnit
are retained under `.data/tutor-repair-phase-20261108/phase1/` and `checks/`.
Runtime identity is provisional until the final new manifest is frozen; no
product registration/default change is made. Final issue tracking, limitations,
substage commits and the unexecuted real-validation proposal follow in REPORT.md.

## Stage 2: complete source negotiation and Mock syntax

`complete-v1` is an additive Java Evidence projection negotiated and echoed even
on CHECK. It returns raw text and its hash with `text_complete=true`, preserving
code structure and suffixes. It rejects upstream-truncated text, rows over8000
Java UTF-16 units, totals over16000 units or32768 UTF-8 bytes, and more than8 rows.
It never returns a complete-labelled prefix. The Python adapter checks policy,
scope, row/hash/completeness and capacity; an older Java server lacking the echo
fails closed. Retrieval normalization and stored Evidence identity are unchanged.
Legacy consumers retain the old normalized/prefix projection to avoid changing
unrelated Study/frozen consumers. Activating the new projection requires the new
explicit Tutor factory; it is not default deployment acceptance.

The explicit v15 factory defaults to a source-preserving, credential-free Mock.
It chooses whole bounded paragraphs, preserves programming brackets, and refuses
when no whole paragraph fits. Its citations still pass the real runtime protocol.
The frozen base Mock remains unchanged: fully fixing the old default would edit a
frozen source or switch defaults, both excluded. A06 is therefore partial across
all identities, fixed in the new candidate only. No monkeypatch or import-time
replacement of the old default is used.

Stage2:16 Python tests and24 Java tests passed, zero skipped. Java tests use actual
StudyEvidenceAuthority with H2 facts and mocked deterministic sources/retrieval;
Python tests use signed Mock HTTP negotiation and real disposable PG. Full
Java↔Python validation is reserved for the final cross-service stage. No model,
embedding or reviewer call is made. `bounded_app:create_app` is opt-in only.

## Stage 3: observations, context and explicit semantic limits

Each answer/evaluation block must carry an actual literal anchor in its bound,
current-turn authoritative source. Missing anchors and obvious unobserved
execution claims produce one support-repair observation using ordinary remaining
slots, then fail closed. This does not add a paid reviewer or call budget.
Rendered fields say `Unverified course text`; derivations are separately
labelled. The contract distinguishes supplied-source attribution from independent
execution. It does not hardcode the spreadsheet/Python answers.

Obvious full-solution cues (code fences, assignment, explicit answer/result labels,
including selected Chinese labels) in Socratic text are rejected/repaired. This
is a conservative heuristic with false-positive/false-negative risks, not semantic
hint validation. Two negative fixtures deliberately retain the limits: an
unsupported influenza claim with a real anchor, and a paraphrased full solution
without a cue can publish. Their test PASS records an unresolved defect, not
learning quality. A03/A12 remain partial and block a semantic-quality claim.

The new runtime retains full completed session messages, answer tails and feedback.
Its existing byte/call/session caps reject an over-capacity context before provider
entry; it never silently extracts a summary prefix. This can terminate a long
conversation earlier, rather than promise all40 turns fit. The new opt-in lexical
snapshot authority exposes empty positive-match results instead of arbitrary first
rows, supports deterministic CJK bigram overlap, and leaves old identities and the
actual product dense retriever unchanged. Retrieval quality remains NOT_RUN.

The first stage3 run passed28 tests. The next run found four maximum-field
failures: the added attribution label made worst-case evaluation501 characters.
The stage3 commit prematurely described that run as passed. The correction keeps
the500 limit and shortens only the new label, then reruns all29 tests. The failed
run and the inaccurate intermediate commit remain visible; final verification
must use the corrected terminal record.

## Stage 4: recovery and accounting

The Vue panel reconciles a restored client ID, text and mode before applying
exhaustion guards. Completed/failed/cancelled confirmations clear pending state;
conflicts and absent exhausted requests preserve the draft and expose recovery.
A confirmed result requires no second TURN. Existing same-ID retries still use
the idempotent server path. The former audit diagnostic is now a recovery
regression; its original source/results remain in commit7c913ec and private audit
artifacts, which are not rewritten.

V15 stores per-call reservation/response/usage states in the existing JSON
checkpoint. It persists known numeric usage before the cancellation/publication
guard, never the cancelled candidate. Unknown usage is null with an explicit
unknown state, not zero. Runtime reservations are never refunded; conservative
external ledger reservations/settlements are separately correlated by call ID.
Supplier invoices are not inferred. The source-preserving Mock is explicitly
nonbillable. A received response replays without resending its call; unresolved
reserved outcomes fail closed across restart. No table/column migration is made.

The opt-in factory requires a separate `TUTOR_V15_DATABASE_URL` with a non-public,
exclusive schema; it rejects public/legacy-public Tutor tables. Never share that
schema with a frozen worker. This operational isolation is necessary because the
frozen worker cannot recognize the new tool contract; no default or worker is
silently switched. Full mixed-worker admission would require a migration and is
outside this phase.

Stage4 final targeted regression:35 Python tests and24 Vue tests passed, zero
failures/errors/skips. The earlier34-test Python and21-test Vue runs are retained.

## Stage 5: frozen candidate, actual chain and final review

The frozen candidate manifest binds twelve runtime/protocol/contract/entry files
at SHA-256 `fe805deee6282e5cd0993b48d76d3500103a3933a36da3e2d5aab919b6955e30`.
Final review added a predispatch guard, explicit prepaid-not-dispatched accounting
and corresponding cancellation/recovery checks before that freeze. No core file
changed after freezing or after the final regressions.

Final verification:43 new Python checks,249 inherited Python mechanism/asset
checks,25 historical replay diagnostics,35 Java checks including the actual
Java↔Python HTTP/authority/PG path, and343 Vue checks; all passed without skips.
Vue typechecking also passed. A separate consumed-development Mock16 run completed
all16 positions with32 simulated requests and a reconciled mirrored ledger.
None of those outcomes establishes real generation or semantic improvement.

The prospective16 packet was authored after candidate freeze and has not run
through the candidate. It has exact source quotes and a separate lock and empty
rating template, but no independent human gold labels. The only future paid
proposal and its prerequisites are in [FUTURE_VALIDATION.md](FUTURE_VALIDATION.md).
Source/diff re-review, including unresolved semantic counterexamples and initial
harness failures, is in [FINAL_REVIEW.md](FINAL_REVIEW.md).

All108 original retained request bodies replay exactly, all48 scheduled outcomes
and216 ledger events match, and2053 historical files verify unchanged. Retained
parsed proposals are wrapped in reconstructed response envelopes: original raw
response bytes remain unavailable. The phase container was removed after schema
cleanup; all23 pre-existing running containers remain. A first cleanup comparison
mistakenly compared short with full IDs; prefix-normalized verification corrected
that check without touching any other container. Private evidence is retained in
`.data/tutor-repair-phase-20261108/`; final commands and closure are in REPORT.md
and VERIFICATION.json.
