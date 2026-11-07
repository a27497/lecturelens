# V16 zero-cost follow-up

Start: `0a701c34d9ab236d1dd8acad5714618b016c63d3`, clean dedicated worktree.
No real model, embedding or reviewer request is authorized; all cost is US$0.
New behavior uses `p8-tutor-verified-v16-development`; v15 and earlier frozen
sources, identities, results and defaults are retained unchanged.

## Stage 1: reproducible publication defects

Two independently authored tests reproduce v15 publishing (1) an unrelated
influenza claim and invented mastery feedback with real anchors, and (2) a fully
spelled-out solution as a Socratic question. Both run through actual PostgreSQL
runtime publication, not only auxiliary validation. This violates the advertised
source-grounded-claim and answer-withholding contracts. It does not establish a
requirement for regexes to solve unrestricted semantic inference.

V16 removes these two unconstrained publication surfaces. Model-selected course
statements are exact contiguous source excerpts, feedback pairs exact current
learner words with an exact source excerpt, and derivations are bounded numeric /
sequence expressions computed by a pure AST interpreter. No arbitrary code,
names, attributes, comprehensions, I/O or imports are allowed. Rational arithmetic,
bounded lists/tuples and range are generic operations, not course answer keys.
The interpreter proves the selected expression's value only. It does not prove
premises, source relevance, coverage or the learner's inference.

Socratic turns select a grounded hint intent from five controller-owned question
acts. Free answer/feedback text and arbitrary labels cannot be published in that
mode. This prevents the reproduced free-text leak; choosing the right hint and
giving effective instruction still require semantic evaluation. Learners can
open authoritative course citations, which may contain solutions; this is not
an access-control promise to hide the course itself.

The existing1600/500 limits, four distinct canonical citations, call/deadline/
byte budgets, complete source negotiation, cancellation and recovery fences are
unchanged. There is no post-hoc answer truncation, blanket refusal or private gold
in model context. Source extraction can omit necessary context; checked arithmetic
can be irrelevant and controller hints can be too generic. All original mandatory
points and strict grading stay in force. Do not count narrower mechanical validity
as improved tutoring quality or mark A03/A12 fully solved.

The first37-test run had five authoring assertion failures: a canonical hash
contained97, mistaken for a visible solution. The correction isolates answer text
from its required citation marker; failed terminal records remain. Corrected37
checks passed, then generic bounded sequence cases were added. Final phase
results, entry freeze, seven-item statuses and cleanup are in REPORT.md and
VERIFICATION.json when delivered.

## Reference status

`sample-candidate.json` inherits all16 questions, points and gates unchanged from
the prior prospective packet, under a separate version. It is now explicitly
**development-exposed**: its author inspected obligations during v16 design and
matching numeric unit fixtures exist. It is not fresh holdout or independent
human gold. No candidate has executed the packet itself. The second source pass
is by the same Codex author. `reference-review-pack.json` and REFERENCE_REVIEW.md
contain per-question source locations, obligations, ambiguity and scoring checks;
independent reviewer/dispositions remain null/PENDING. Paid admission stays blocked.

## Stage 2: execution and evidence prerequisites

The default diagnostic entry verifies source/contract hashes without DB/transport/
credential access. Explicit live admission additionally checks a fresh bound grant,
declared independent reference review, current pricing/configuration, exact clean
HEAD and frozen code-commit blobs, plus a durable one-use run-ID claim. Mock uses
synthetic16 only. The mirrored ledger bounds all attempts/repairs at80 and local
reserved-plus-settled liability atUS$0.70; unknown outcomes keep full risk and stop.
The raw capture saves bounded HTTP entity bytes before JSON parsing, with known
authorization-secret redaction (including JSON escapes), no headers/exceptions,
and explicit incomplete/redacted status. It never reconstructs historical bytes.

The draft protocol rehearsal passed8 fault/normal tests with identity verification
explicitly stubbed; it is not final identity/freeze acceptance. Publication,
capture, admission and hard-limit regressions passed with real isolated PG.
The actual Java-controller/HTTP/new-factory/authority/PG chain passed35 Java tests,
including two-session isolation, same-ID replay, owner/version and canonical code
binding. Final acceptance must rerun the actual frozen entry without the stub.

All9 historical Ruff diagnostics originated in the previous phase. Frozen old
sources remain unchanged; their exact attribution is in RUFF_ATTRIBUTION.json.
The nine named current-phase Python files pass Ruff with zero diagnostics; no
directory formatting or source-asset formatting is used. Initial current-phase
import/fixture style errors were fixed before freeze.

## Final review rejects this precursor

After the frozen63-test pass, a separate PG reproduction proved that AST comments
were ignored during evaluation but retained in displayed expressions, allowing
`2+2 # unsupported prose`. No v16 frozen source/asset/result is edited to hide it.
The additive v17 runtime closes the full-string grammar gap; the final delivery
is in [the v17 follow-up](../tutor-followup-v17-v1/README.md). V16 is not approved
for live dispatch. Its source-root fence also rejects later source-tree changes;
reproduction uses its recorded code/freeze commits.
