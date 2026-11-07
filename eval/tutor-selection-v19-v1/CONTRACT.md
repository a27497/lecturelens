# V19 selected-source development contract

Parent: v18 identity and frozen three-turn development packet. Historical questions,
references, sources, results and FAIL remain immutable. The copied sample and
reference-review packets are byte-identical to v18; no criterion is removed and no
reference enters model messages. This is a new protocol identity, not a rescore.

## Changed protocol

- Source: `{kind:source, span:{evidence_id,first_unit,last_unit}}`; no source text or
  quotation supplied by the model. Explanation/code: generated `text` plus `span`.
  Calculation: bounded expression plus `span`; feedback: learner quote, text, span;
  Socratic: finite intent plus span. Unit numbering is one-based and inclusive.
- Each unit is a lossless <=200-code-point raw slice. Complete lines are grouped
  when possible; overlong lines are fragmented without discarding any character.
  Every complete Evidence text is sent exactly once in its catalog entry.
- Controller-owned SHA-256 fences the observed source across later searches,
  correction reservation, restart, validation and final publication. Selected
  span offsets/hashes are durable. Unknown/unobserved IDs remain fatal before repair.
- Exactly one finish correction is shared by format, span and inherited recoverable
  support/render errors. Three ordinary decisions plus one correction, at most4
  sends/turn; correction is finish-only. Mixed format/span errors do not gain a
  second allowance. Non-JSON responses, fabricated IDs, unknown usage, source
  changes and exhausted budgets do not gain additional requests.
- Search observations in the request use ordered catalog indices. Complete source,
  history and durable observations are retained. Mode-specific schemas advertise
  only applicable fields. The server continues accepting bounded optional feedback
  on a normal turn; this is not a semantic grading guarantee.

## Unchanged limits and acceptance

Body4096 and evaluation1024 Unicode code points, including all labels and full IDs;
4 answer blocks (text900),2 feedback blocks (text384),4 distinct IDs. Source span900,
explanation support800, feedback support400, hint/calculation support240. No slicing
an over-cap span: reject/correct or fail. Output4096 tokens; request65536/response131072
bytes; at most2 searches/turn;20s deadline; turn64000/session640000 reservation proxy;
session60 model calls. No default identity, database schema or frontend change.

Frozen smoke retains every necessary explanation, condition, trace, commented code,
inside/outside-print comparison, index mapping, withheld-answer hint and contextual
feedback requirement. Correct binding alone never passes semantic quality. A03
unsupported interpretations remain possible and are explicitly adversarially tested.
Finite Socratic acts and the unchanged bounded expression grammar prevent the known
free-solution/comment carriers; no universal semantic guarantee is asserted.

## Offline evidence interpretation

The v18 failed smoke's first three original captured response entity bodies can be
replayed unchanged through the new HTTP channel. The requests now use the new schema;
this is response-body replay, not reproduction of original requests or a new model
success. The fourth full teaching response is **authored Mock content**. Subsequent
default Mock turns only verify mechanics. A separately retained parsed runtime replay
has the same disclosure. Older parsed-only assets remain reconstructed replays.

The same Codex author reviewed source alignment, wrote implementation and supplied
fixtures. This is nonblind AI self-review, not independent human review or agreement.
