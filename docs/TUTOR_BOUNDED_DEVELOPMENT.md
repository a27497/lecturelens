# Bounded Tutor development candidate

`p8-tutor-bounded-v15-development` is an explicit experimental path. Its product
factory installs only `SourcePreservingMock`. Real task quality, cost improvement,
human agreement, SQL holdout, scaling and learning effects are NOT_RUN. The
frozen/default P8 runtime and old evaluations remain unchanged.

The learner goal remains a source-grounded explanation or guiding question. A
model selects up to two evidence searches, observes the results and submits
source-bound blocks or a clean insufficient-evidence outcome. Missing literal
anchors or obvious solution/execution cues can change the next decision through
one bounded support observation. Final answer, canonical citations and checkpoint
commit atomically. Authority/version/deletion, deadlines, persistent budgets,
cancellation and unknown-outcome stops remain enforced in Python/PostgreSQL.

## Contracts and limits

At most four answer blocks have300 text characters each; at most two feedback
blocks have160. Each binds one currently observed canonical ID of at most64
characters and a literal source anchor of at most240. Rendering adds the full
canonical marker and explicit source/derivation attribution. **All** displayed
characters count toward the unchanged1600/500 answer/evaluation limits. There
are no short reference aliases, post-hoc truncation or extra format-repair calls.
The four-distinct-ID limit still covers both fields together.

Literal anchor existence is mechanically checked. It does not prove that a
paraphrase follows from that anchor. The Socratic cue filter catches selected
explicit answer labels/code/assignments, with false positives and bypasses.
Counterexamples remain in tests. The displayed attribution distinguishes course
statements and derivations from independently executed facts; no execution tool,
automatic grading or mastery inference is added.

Full prior completed messages, answers and feedback are retained for the current
bounded session, including tails. If the whole request exceeds the existing turn
or session cap, dispatch fails before provider entry. The runtime does not
promise40 large turns will fit or claim long-term memory. Offline snapshot
retrieval returns an empty observation for zero positive token overlap; this is
not a real embedding-relevance result.

## Complete Evidence and compatibility

The new Python authority negotiates `complete-v1` on CHECK/SEARCH/READ. Java
echoes the policy and returns raw text, content hash and completeness. Limits are
8000 UTF-16 units per row,16000 total units,32768 total UTF-8 text bytes and at
most8 rows. Ingestion-truncated or over-capacity sources fail explicitly, without
an advertised complete prefix. The adapter rejects missing policy, bad hash,
incomplete rows and scope mismatches. Old servers therefore fail admission.

Java retrieval normalization and stored Evidence IDs are unchanged. Legacy
consumers retain their frozen normalized/prefix view; the new projection is an
additive negotiated option. The old Mock also remains frozen and can still
rewrite brackets; the new factory's default Mock preserves whole bounded source
paragraphs and valid indexing. Default-path activation is outside this phase.

## Isolation and accounting

Factory: `lecturelens_real_eval.tutor.bounded_app:create_app`. It requires
`AGENT_LLM_MODE=mock` and an explicit `TUTOR_V15_DATABASE_URL` with a dedicated,
non-public schema. It checks admission before base startup and rejects public or
legacy-public Tutor tables. Operators must not point frozen/new workers at the
same schema; full mixed-worker admission would need a separately reviewed
migration. The phase neither deploys this factory nor changes an existing worker.

The existing JSON checkpoint retains call reservation, response and usage states.
Known usage can persist after cancellation/deadline, while the answer still fails
the publication fence. Unknown usage is null, not zero; known pre-dispatch stops
are marked not-run. Runtime byte-proxy reservations are not refunded. External
PG/JSONL ledger reservation/settlement amounts are correlated separately, with no
supplier-invoice claim. Mock calls are explicitly nonbillable. A received response
can resume without resending; unresolved reserved outcomes fail closed.

The Vue panel reconciles a restored client ID/text/mode before session exhaustion
disables retry. Confirmed terminal results unlock navigation without another TURN.
Conflict/absent pending states preserve the learner's draft.

Implementation/validation evidence, issue closure and the unexecuted future trial
proposal are in [the phase report](../eval/tutor-repair-phase-v1/REPORT.md).
