# Python notation contract resolution

**R1 is resolved for the new explicit development candidate; no real trial is authorized or executed.**
This is Codex implementation/review with hand-constructed fixtures, not independent human expert annotation.
The original [review and issue](../tutor-public-review-v1/REVIEW.md) and DEVELOPMENT_REVIEW.json are unchanged.

## Root cause and bounded change

Started at clean `6775d1100acb1cd9229c7a9cabeb7d86e21f7377` on `codex/tutor-scale-preparation`, in
`/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens`. No other checkout was inspected or changed.
Read AGENTS.md, the public dataset/review and v1/v2 evaluation contracts, Tutor instructions/parser,
publication authority and P8/P10 identity implementation before editing.

The historical [P8 account](../p8-tutor/REPORT.md) records the original `Adj[u]` citation false positive.
The parser was subsequently narrowed to evidence IDs, but v9 retained two instructions replacing bracket
indexing with parentheses. That stale instruction conflicts with valid NumPy syntax and four unchanged
development rubrics. It is not a demonstrated real-model failure or a hard parser rejection.

Only an additive runtime subclass changes the system text and finish-tool description. It allows ordinary
programming brackets and preserves citation-ID syntax, observed-ID/authority validation, four-ID and output
limits, abstention, repair and budget rules. Request reservation uses actual replacement message/schema
bytes; code and tool schemas retain their existing semantics. The parser itself is unchanged. ID-shaped
tokens such as `[e999]` and `data[e1]` remain candidates even in code; non-ID brackets are ordinary text.
This intentionally prevents a code-fence escape from citation validation. An answered turn still needs
valid observed citations; malformed/non-ID markers alone cannot satisfy that requirement.

The final identity is **p8-tutor-python-notation-v10-development-r2**, registered by [candidate.json](candidate.json),
SHA-256 `8f430ba637bb13dfd415bf29d4785e116d44141d7d3c49946ede77cee45079cf`.
Use the explicit `lecturelens_real_eval.tutor.python_runtime:PythonTutorRuntime` entry point after verification.
Historical v9 remains byte-identical, importable and verifiable; existing public Mock drivers and product
defaults still select v9. Its original instruction conflict is not retrospectively relabeled as fixed.
No product configuration, live adapter, scoring implementation or historical frozen hash was changed.

An intermediate draft at `a6d331d72cbb6768282ef92e46326ba86cf07511` used task-specific syntax examples.
Self-review removed these to avoid embedding the evaluated answers in the system prompt. Final revision
`af44fa534bced28cedb9a6d0e2530c92677170ab` uses generic variables/bounds, adds a non-leakage assertion and
registers the distinct r2 identity/scope hashes. The draft commit and its validation remain in Git/raw records.

## Actual verification and coverage relationship

| Code version | Actual check | Result |
| --- | --- | --- |
| `a6d331d` | New contract 47; historical Tutor 122; citation grammar 25; P8 runner/reviewer Mock 84; frozen identity checks 10 | **288 passed**, 0 failed/errors/skipped, 147.78 s |
| `af44fa5` | Final contract 47; citation grammar 25; P7/P9/P10 and development/historical identity checks 10 | **82 passed**, 0 failed/errors/skipped, 8.49 s |
| `af44fa5` | Existing synthetic v1 tools 11, v2 tools 23, public tools 10 | **44 passed**, 0 failed/errors/skipped, 4.28 s |
| `af44fa5` | Ruff lint/format of the three new Python files; read-only frozen scope validation | Passed |

Counts overlap; they are not 414 distinct tests. Both runtime suites report one existing Starlette/AnyIO
deprecation warning. The r2 change affects only new prompt examples/assertions, identity metadata and docs;
all inherited controller, parser, store, authority and runner bytes are identical across the two tested SHAs.
Therefore the 288-test historical regression remains applicable, with final prompt behavior covered by the
82-test targeted rerun. The final delivery commit adds only REPORT.md and VERIFICATION.json to `af44fa5`;
it changes no tested code, manifest, dataset, scope or fixture.

All pytest executions used the existing bounded check supervisor and `scripts/eval/check-study-offline.py`:
provider configuration stripped, startup guard asserted, Python sockets restricted to the verified local
database/ephemeral loopback fixtures. The main check had a 360 s limit; final targeted/tools checks had
180/120 s limits. No timeout or cleanup failure occurred. Network counter files report zero denied
connections; these audit Python sockets, not libpq C connections or a global packet trace. No real transport
was selected: fixed providers or `httpx.MockTransport` supplied all model/reviewer-shaped responses.

Before starting the existing dedicated DB, verified compose project/path, pinned image, no dependencies,
loopback-only 25841 binding/free port, sole-owned named volume and available resources. Container limits
were 0.5 CPU / 384 MiB. Confirmed the synthetic role and dedicated test/acceptance DBs after start. Tests
used owned temporary schemas, not business/production tables. Zero `python_contract_*` schemas remained;
the dedicated container was restored to **exited 0**, with its volume retained. No other service was changed.

The final fixed-answer records contain **15 completed turns / 30 deterministic decision calls**, from
four session prefixes (4, 3, 4, 4 turns), two development courses, and two canonical abstentions. This is
not a new 15-turn dataset or four complete sessions. It includes all eight prospective pilot turns and:

| Unchanged task | Constructed legal answer exercised | Source lines in retained Python material |
| --- | --- | --- |
| `python-01:3` | `data[29, 19]`, zero-based row/column interpretation | 132, 202 |
| `python-02:1` | `data[0:4, 0:10]`, excluded stops, shape 4 by 10 | 246, 257 |
| `python-02:3` | `data[:3, 36:]`, retained rows/columns and shape 3 by 4 | 173, 281, 287 |
| `python-04:4` | `numpy.hstack((A[:, :1], A[:, -1:]))`, preserving two dimensions | 642, 649, 655 |

Source lines resolve into authoritative unchanged evidence blocks. Each case passes AST syntax checks,
runtime publication, citation extraction/authority checks and existing annotation/scoring compatibility.
Earlier turns preserve original learner text/history; ordinary spreadsheet QA and insufficient-evidence
turns provide non-code regression. Controlled search observations deliberately isolate publication, not
retrieval quality. Fixture labels remain explicitly hand-constructed and produce MOCK_NOT_QUALITY.

Additional negatives cover 27 plain/inline/fenced ordinary-code combinations, four provider-level forged-ID
cases (checked before schema rejection), five PG publication failures mixing code/valid/foreign citations,
and three PG failures where absent/malformed markers cannot replace a required citation. Expected failures
remain failed with no published answer. Manifest/source drift, holdout substitution, changed scope hash and
incomplete sessions are rejected. An initial precommit test failed because two separate inline snippets
were represented as one multiline fixture snippet; splitting those snippets fixed the test, followed by
47/47 passing. The initial failure log is retained, not treated as a model-quality trial.

Independent artifact recount confirms 15 unique turn keys and 74/74 pre-existing evaluation files unchanged.
Original runtime bytes are additionally covered by the historical manifest checks. Questions, references,
sources, split, original blind sample, prior identities and original result directories were not edited.

## Frozen prospective scope and remaining boundary

[development-pilot-v1.json](development-pilot-v1.json) freezes **python-01 (4 turns) + sheets-01 (4 turns)**,
one shortest complete session from each development course. It pins `tutor-public-v1`, its data/split lock,
session hashes and exact ordered turn keys, plus the r2 candidate digest. [scope-lock.json](scope-lock.json)
pins the plan SHA-256 `27c3361d841412f950b9aac5ab08a0d14e40b4fb0bc60801be0c9d181e5180d7`.
The prior full development source audit found no mandatory factual reference blocker; this turn verifies
the four affected contracts and surrounding fixture cases, not a new full 40-turn expert audit.
No SQL candidate execution or holdout-result tuning occurred; structural dataset verification is separate.

Reproduce the read-only preflight from the repository root:

```bash
agent-service/.venv/bin/python eval/tutor-python-contract-v1/contract_check.py \
  --plan eval/tutor-python-contract-v1/development-pilot-v1.json
```

The plan has `execution_authorized: false`. A future real adapter must explicitly select the new identity
and complete scope; it cannot reuse the synthetic live route or budget-truncate sessions. Tutor/reviewer
exact model IDs, reviewer switch, retry rules, total provider-call hard cap and monetary hard cap still
require the user's separate confirmation. Prices and account balance are **UNKNOWN**. Persistent call/token
reservations do not themselves prove a monetary ceiling; confirmed pricing/conservative reservations and
an enforceable money policy are prerequisites. No provider/account credentials were inspected and no trial was started.

Raw artifacts: `.data/tutor-python-contract-v1-20261107/` (JUnit, fixed answers/requests/fixture scores,
scope output, resource preflight, historical hashes and verification summary). Supervisor records:
`.data/dev-checks/python-contract-{targeted-draft,targeted-ready,committed-regression,r2-final,tools-compat}/`.
[VERIFICATION.json](VERIFICATION.json) records exact checked SHAs, hashes, counts and raw record paths.

**NOT_RUN:** real Tutor/reviewer/embedding calls, real answer/citation quality, human agreement/kappa,
real token usage/cost, learning effects, video/ASR/Chinese capability, stress tests and live/deployment paths.
The historical mutation harness was not executed because it rewrites frozen source/manifests; tampering
tests instead mutate temporary copies. No broad product-stack run was needed for this additive variant.
