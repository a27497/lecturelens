# v14 source restoration and zero-cost entry verification

**PASS — zero-cost actual-entry preflight and regression.** Final collection and
execution both confirm **249 tests: 249 passed, zero failures/errors/skips**.
Validated implementation: `4e30c1765e1efd354c2180a1849a8eb6d2336111`.
Supervisor exit 0, 189.522s; pytest 187.49s, with three existing loader/deprecation
warnings. Actual CLI preparation exits 0; fenced `--live` exits 2 before dispatch.

This stage restores the original source bytes and protects frozen evaluation
assets. **Real model/embedding/reviewer requests: zero. Cost: USD 0.** The existing
v14 identity, Tutor behavior/prompts/defaults, source hash expectations, questions,
references, thresholds, freeze-lock and prior failed reports remain unchanged.
There is no real task-quality or cost-improvement claim.

Started clean at `e4699e8e9144df50482eb671f89cebd1bf07cdf8` in the requested
worktree and branch. This report supplements the rejected preparation; it does
not rewrite its outcome, call count or invalidation record. Exact final code
version, command records and results are in `VERIFICATION.json`. The delivery
commit adds documentation and non-sensitive verification after the tested code.

## Restored asset and provenance

Only `../tutor-v14-fresh-v1/materials/carpentries-python-new.md` was misformatted:
seven code lines across four diff hunks changed single quotes to double quotes
and removed spaces around `**`. The spreadsheet episode and both licenses already
matched their recorded hashes and were not rewritten. The rejected version
remains recoverable from the starting commit and a new private diagnostic copy.

| Python episode05-loop | SHA-256 | Bytes |
| --- | --- | --- |
| Rejected formatted file | `dd472a2a972b5b25a24b120a9da4ce8a79cdd3e3df89ace7e62873894c02c206` | 10,861 |
| Restored original / frozen expectation | `59ad81e33ec8881f3a8bafb8f220ec5b9bea8af6e9caee7fbdefffaa703ffc53` | 10,863 |

Restoration uses the previously retained, hash-verified
`.data/tutor-v14-real-20261107/python-original-source.md`. Its 17-file historical
artifact manifest was verified first. That copy was fetched in the prior stage
from `swcarpentry/python-novice-inflammation`, immutable revision
`eb18f246aee338b2a6169ba18d8c5ced7cf89f53`, path `episodes/05-loop.md`, and exactly
matches the unchanged `sources.json` expectation. No credential or network fetch
is needed to restore it. The copy is written byte-for-byte without newline,
encoding or formatting conversion.

All twelve top-level frozen file hashes and all four source/license hashes now
match. `freeze-lock.json` remains
`ba3d1b14dd410e770b2cdfd062e3c7042d93d70a32c27b61d871472aecb390a0`;
the plan remains
`f28b9bae8fd653ed09922ec5a451a7b629e98b5c6c32dec45c6077027dfb2576`;
the v14 candidate remains
`180929dee65677f105b1d9c85705394b28b8dc90a0edef2e99abc140821420b3`.
No sample/reference projection or hash regeneration occurs. Original source
whitespace is retained; do not clean it to satisfy a whitespace checker.

## Why formatting reached the source, and the protection

The installed **Ruff 0.16.7** includes `*.md` by default. The prior config had no
evaluation exclusion, and `force-exclude` defaulted to false. Directory-wide
`ruff format --config agent-service/pyproject.toml eval/tutor-v14-fresh-v1`
therefore formatted Python fences in Markdown as well as editable Python files.
Local tool configuration output is retained. A scratch-only regression applies
the exact old config to the restored original and reproduces the exact rejected
SHA above; this is measured behavior of this installed tool, not an assumption
about all Ruff releases.

Minimal guard changes:

- `agent-service/pyproject.toml` adds recursive `**/eval/**` and `**/.data/**` exclusions and
  enables `force-exclude`. Explicit file arguments also respect these protections,
  including frozen Python evaluation code and private records.
- `eval/ruff.toml` inherits that config and excludes its entire evaluation tree
  with `force-exclude`, protecting automatic configuration discovery too.
- The local execution guide now requires explicit editable Python paths. New
  maintenance checks live in `scripts/dev/`, outside frozen bundles. No CI,
  production setting or Tutor default changes.

These guards apply to Ruff formatting and fixing. They do not replace the runtime
source/identity fences. Tests run directory/explicit-file formatter commands only
on disposable mirrored trees, including deliberately unformatted protected-code
sentinels. All protected file hashes must survive unchanged. A separate ordinary
editable Python file must still format, proving formatting is not globally
disabled. Live source assets are never used as formatter test targets.

Only the new editable check paths were formatted:

```sh
agent-service/.venv/bin/ruff format --config agent-service/pyproject.toml scripts/dev/test_v14_assets.py scripts/dev/check_v14_assets.py
```

## Actual-entry preflight and regression scope

The guarded harness calls the unchanged `run_fresh.run()` before pytest and
records its actual `PREPARE_ONLY_NO_EGRESS` result. New tests additionally invoke
the real CLI in a child process, checking the complete identity/source/reference/
plan chain and 16 positions. The original formatted bytes and content
mutations of each of the four source/license assets are rejected through the
actual entry, before DB construction/output creation. The tests do not substitute
a hash-only checker or replace frozen expected hashes.

The final suite comprises the original **219** tests (33 v14, 46 v12-entry, 18 v13 and
122 Tutor), the unchanged **17** fresh-entry tests, and **13** new asset/formatting/
CLI guard tests. All are collected explicitly; no frozen test or lock is edited.
The existing full16 Mock cases cover normal completion, local failure/dependency
skip/independent-session continuation, auth/unknown-usage/global call/fee stops,
reviewer-off settings, unchanged protocol AST and PG/JSONL event agreement.
Retained-response replays prove mechanics, not model quality.

The clean `safe_exec` interpreter strips provider/proxy environment, denies
external DNS/sockets and allows only the dedicated PG/ephemeral test loopback.
Tests reject credential lookups and real HTTP transport. All execution uses
MockTransport or retained parsed responses. A test-only `LECTURELENS_REAL_EVAL=1`
lets the frozen live-fence test reach the offline fence after its earlier opt-in
check; it does not copy credentials or permit dispatch. Another regression
removes it and verifies `REAL_EVAL_SWITCH_REQUIRED`. Actual CLI `--live` inside
the fence exits 2 before any output/ledger/send. No private live sender is run.

Final supervised commands, differing only in collection mode/output directories:

```sh
python3 scripts/dev/run_check.py --name v14-assets-collect-v2 --timeout 1200 --output .data/tutor-v14-asset-recovery-20261107/checks -- agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-v14-asset-recovery-20261107/network-collect-v2 scripts/dev/check_v14_assets.py --output .data/tutor-v14-asset-recovery-20261107/collection-v2 --collect-only
python3 scripts/dev/run_check.py --name v14-assets-final-v2 --timeout 1200 --output .data/tutor-v14-asset-recovery-20261107/checks -- agent-service/.venv/bin/python eval/tutor-scale/safe_exec.py .data/tutor-v14-asset-recovery-20261107/network-final-v2 scripts/dev/check_v14_assets.py --output .data/tutor-v14-asset-recovery-20261107/final-v2
```

Full command/terminal records, collection inventory, JUnit, source restoration
diff, actual entry/CLI observations, scratch formatter reproduction and all
Mock/replay evidence are retained under
**`.data/tutor-v14-asset-recovery-20261107/`**. Mock/replay ledger amounts are not
new provider charges. Original failed-batch evidence and the previous 1,028-file
offline evidence are rechecked without overwriting either.

The final evidence manifest covers **2,356 files** with SHA-256 digests. All twelve
guarded Python process records report zero socket/DNS denials and zero Python
connections; libpq accounting is discussed below. Final Ruff checks on the two
explicit editable scripts and scoped whitespace checks pass. Read-only PG
reconciliation matches 68 historical events, 13 turns and 4 sessions. Cleanup confirms
the dedicated PG exited0, port 25841 closed, its volume retained and all 23 original
running containers still running.

## Preserved initial check failures

The first full run at `cbc6785503219bb0c08f9a8d1247cea770e29bd5` passed 246
and failed 3 new checks. All original 219 and frozen 17 entry tests passed. Two
formatting checks exposed that `../eval`/`../.data` exclusions did not protect
explicit cross-directory targets. The third check named a copied project config
`original-pyproject.toml`, which Ruff parsed as a standalone config and rejected.
These are retained under `checks/v14-assets-final.*` and `final/`; no source or
historical expectation is changed to hide them.

The corrected config uses recursive asset-path globs. The reproduction fixture
keeps the recognized `pyproject.toml` name. Formatter mirrors are created in
owned, automatically cleaned temporary directories outside real `.data`, so a
`.data` ancestor cannot mask a missing eval exclusion. Commands, outputs and
before/after hashes remain in this stage's evidence. The focused 13 checks then
passed; the full 249 collection and execution are repeated at
`4e30c1765e1efd354c2180a1849a8eb6d2336111`. The final delivery changes only report
and verification documents after that implementation version.

## Operational boundary and readiness

Database checks use the existing dedicated, loopback-only, resource-bounded PG,
with separate disposable schemas. Read-only reconciliation checks the historical
run's 68 events, 13 turns and 4 sessions against its retained snapshot. Python socket
counters do not count libpq connections; actual PG transactions/tests establish
database coverage. The exact temporary PG is stopped after checks, its evidence
volume retained, and original running services are preserved. No other workspace,
SQL holdout, production/student/manual-account data, credentials, push, PR, merge,
deployment or CI is involved.

Passing source and mechanism checks permits **requesting new real-validation
authorization**, not dispatching. The prepared 16 positions remain the same frozen
development batch. A future approved execution still needs clean committed code,
the complete entry checks, isolated DB and execution-date verified compatible
rates. Neither old `execution_authorized` metadata nor unused prior money grants
permission. No new sample generation, paid probe, rerun or expansion occurs here.

**NOT_RUN:** real v14 quality/compression/exclusivity efficacy, real cost change,
SQL holdout, independent human agreement, expansion and learning effects.
