# Python notation contract: development candidate v10

Resolution of R1 in [the unchanged source audit](../tutor-public-review-v1/REVIEW.md).
The v9 prompt still required parentheses for indexing, although its citation parser already recognized only
evidence-ID-shaped bracket tokens. That restriction originated with the earlier `Adj[u]` false positive
([historical account](../p8-tutor/REPORT.md)); valid Python indexing is incompatible with that instruction.
This was a contract conflict, not a reproduced real-model failure.

## Explicit identity, unchanged historical behavior

`candidate.json` registers **p8-tutor-python-notation-v10-development**, entry point
`lecturelens_real_eval.tutor.python_runtime:PythonTutorRuntime`. It inherits the frozen v9 controller and
changes only the system instruction and finish-tool description. Request budget reservation includes the
actual replacement message/schema bytes, including repair requests. Parent prompt drift fails closed.
No scoring requirement, question, parser, authority check, limit, transport or product/default entry is changed.
Historical v9 remains importable and verifiable; existing public Mock entry points still select v9.
Future execution must explicitly select this new class **and** verify its manifest; this is not a live adapter
or authorization to execute one. No deployed/default identity has switched.

The new instruction preserves `data[29, 19]`, `data[0:4, 0:10]`, `data[:3, 36:]` and dimension-preserving
slices in prose, inline code and fenced code. Course citations retain `[evidence_id]` syntax and the existing
requirements: observed authoritative IDs, at most four distinct IDs, grounded answered turns and canonical
abstention when evidence is insufficient. Ordinary brackets are not citations. **ID-shaped tokens remain
citation candidates inside code**, including `data[e1]`; descriptive index names avoid this reserved lexical
ambiguity. Code markup cannot hide forged IDs. Malformed/non-ID markers cannot replace a required citation.

`contract_check.py` reuses the historical P8/P10 and synthetic v1/v2 preflights, then verifies the new manifest's
exact file set and hashes. Its parent pins remain unchanged. It is a local validator and never sends requests.

## Frozen prospective scope (not authorized)

`development-pilot-v1.json`, bound by `scope-lock.json`, selects **python-01 and sheets-01**: two development
courses, two complete sessions, **4 + 4 = 8 turns**, in that order. Dataset `tutor-public-v1`, data-lock,
split, per-session turn hashes and exact turn keys are retained. It excludes SQL and never truncates a
session according to remaining budget. Validation refuses drift, missing sessions or holdout substitution.
No factual reference blocker remained in the preceding development content review; R1 is resolved here at
the instruction/parser/scoring-contract level. These eight turns are only an initial mechanics/quality probe,
not representative coverage of all four affected Python tasks or of course generalization.

```bash
# Repository root; read-only, no database or provider required:
agent-service/.venv/bin/python eval/tutor-python-contract-v1/contract_check.py \
  --plan eval/tutor-python-contract-v1/development-pilot-v1.json
```

The scope has `execution_authorized: false`. Tutor/reviewer exact model IDs, reviewer enablement, retry
policy, total call hard cap and monetary hard cap remain **unconfirmed**. Prices and account balance are
unknown. Eight scheduled turns are not a provider-call cap: search, finish, repairs, retries and optional
reviewer calls add calls. Existing persistent call/input/output reservations bound execution; a monetary
stop additionally requires confirmed model-specific pricing, conservative reservations and an enforceable
budget policy. Call count alone is not a money ceiling. No real adapter or budget authorization is added.

## Bounded no-cost verification

The regression fixture contains 15 **hand-constructed Codex answers/decisions**, including all four affected
tasks (`python-01:3`, `python-02:1`, `python-02:3`, `python-04:4`), their preceding context, ordinary spreadsheet
QA and two abstentions. Source-line locators resolve into unchanged authoritative evidence. Controlled
observations isolate publication/contract checks; this does not test retrieval or model reasoning. Fixture
labels exercise the existing annotation validator/scorer and are not human annotations or measured quality.

Tests cover AST-valid Python, plain/inline/fenced brackets, mixed citations, forged IDs before provider
schema checks, authoritative publication rejection, missing/malformed citations, request-byte budgets,
complete development scope and tamper rejection. Existing v9/P7/P9/P10 checks remain separate regressions.

For PG tests, first inspect the dedicated stopped container's compose path/project, pinned image, loopback
25841 binding, sole-owned volume, dependencies and available resources. Do not assume any running DB is safe.
Only the dedicated `lecturelens-tutor-scale-prep-20261107-postgres-1` is eligible; retain its volume and restore
its initial stopped state. Tests use the synthetic `tutor_scale` role, `lecturelens_agent_test` (historical
P8 tests also use the dedicated acceptance DB), fresh owner/course IDs and owned temporary schemas.
Do not use account credentials. Run under the existing socket fence and bounded local check supervisor:

```bash
# Set AGENT_TEST_DATABASE_URL to the verified isolated synthetic test DB, never a product DB.
agent-service/.venv/bin/python scripts/eval/check-study-offline.py --database-port 25841 \
  --network-records .data/tutor-python-contract-v1/network-NEW -- \
  -q tests/test_tutor_python_contract.py tests/test_tutor.py tests/test_tutor_citations.py \
  tests/test_p8_tutor_eval.py
```

See [REPORT.md](REPORT.md) for actual commands/results and omissions. No real provider, embedding or reviewer
is called. Real quality, human agreement, real token/cost and learning outcomes remain **NOT_RUN**.
