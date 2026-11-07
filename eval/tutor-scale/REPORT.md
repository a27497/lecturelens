# Tutor scale preparation verification

This record reports Mock mechanisms only. Real model execution, real citation quality, real human agreement,
real usage/cost and learning outcomes are NOT_RUN. No service deployment, load test, CI change, push or PR.

The verified remote main is `300be51515867f7ece4f3a9224a484e825219ee0` (`git ls-remote origin refs/heads/main`,
2026-11-07). The source checkout's local `main` points to `fd8ece82`; it was not used or moved. The independent
workspace is `/home/dev/.codex/worktrees/tutor-scale-prep/lecturelens`, branch `codex/tutor-scale-preparation`.
The source checkout remains on `codex/p14-system-model-management` with its existing six uncommitted entries.
Only committed main contents and committed supervisor `b82bebf` were used; no other checkout's edits are inputs.

Resource preflight: approximately 13 GiB available memory, 45 GiB free disk, load below 1.5. The dedicated
`lecturelens-tutor-scale-prep-20261107` PostgreSQL project uses only loopback 25841, synthetic role/account data,
0.5 CPU and 384 MiB. No existing container, account or database was changed. Locked package installation
needed a package download because the offline cache was incomplete; no model or media was downloaded.

## Reuse and historical evidence

The existing P8 runner hardcodes its original snapshot, 24-dialogue input verifier and full-suite size.
`run.py` therefore adds a dataset driver while importing the original TutorRuntime/Store, SnapshotAuthority,
TutorProvider, review_turn, Channel, Ledger and TutorPolicy. The authoritative checks, persistent bounds,
checkpoint behavior and candidate pins are unchanged. No product source or historical eval file was edited.

The audit report at `/home/dev/reports/lecturelens-audit-2026-11-07/` was read before implementation.
P5/P7/P8/P9/P10 documentation and source are present in verified main; P7 ancestry is included via P8.
The old P8 README says v9 live NOT_RUN, while the end of its REPORT records a later live trial. The original
local `p8-ctx-v9-full-20261027` summary/dialogues/reviews were read without executing anything:
18/18 P8 frozen pins match main, manifest matches summary, and files have 24 dialogues / 80 turns / 80 reviews.
The `probability-l2-1:3` unsupported review is retained. No original label or verdict was rewritten.
Historical accounting/invoice correctness was not independently certified and no old ledger was resumed.
Raw historical files remain in their original ignored location; only hashes and structural verification are
recorded in this task's ignored audit artifact.

## New assets

Four explicitly synthetic microcourses, 64 distinct scenario sections, 64 sessions / 320 unique learner
messages: 3 development courses (48 / 240), one course-disjoint Energy holdout (16 / 80). Original CC0-1.0
source, exact evidence locations, references, negative behavior and rubric are committed. This is a synthetic
preparation corpus, not real-course generalization evidence. Holdout tasks have never been evaluated with
an external model or used to modify product prompts/runtime.

Blind review is preregistered at 100 primary assignments and 20 independent overlaps per system. No people
have annotated the outputs. Scoring arithmetic uses hand-constructed fixtures only. Missing/failed execution
results and empty annotations remain visible and cannot become successful quality judgments.

## Trial record

Initial preflight `smoke-initial` failed on author-file hash after formatter changes; no request was sent.
`smoke-final` completed only 8/20 turns: the new custom evidence IDs were outside the frozen citation grammar,
causing 12 `TUTOR_CITATION_MISMATCH` failures. These trials and manifests remain in `.data/tutor-scale/`.
Only data identifiers changed to the already-supported SHA-256 form; no parser/product change or semantic
reference relabeling. Dataset version is now `tutor-scale-synthetic-v2`. `smoke-sha-ids` completed 20/20
turns and 60 fake requests. Subsequent metadata/annotation changes receive a fresh tooling identity.

## Final verification

The final executed tooling commit is `973613876d6d58e332da7b80547a6f48c671e6a3`.
Candidate manifest SHA-256: `8e6aac7da6bb90d727f5b5ca99820deb6fc1e79df20a5e364b719c64e96af84f`.
The final documentation-only commit records this evidence without changing those executable inputs.
Machine-readable counts, fixture arithmetic and artifact hashes are in [verification.json](verification.json).

* 231 existing P8/Tutor/citation tests plus 11 final tooling tests passed: **242 distinct tests**, zero failures
  or skips. The earlier 239-test invocation included the then-eight tooling tests; it is not an additional
  independent 239 cases. One upstream TestClient deprecation warning was retained.
* Final smoke: four sessions / 20 turns / 60 fake requests, COMPLETE. Final full run: four courses /
  64 sessions / 320 turns / 960 fake requests, COMPLETE, no missing results or protocol failures.
* Independent `verify.py` reconciliation confirms all course/session/turn/holdout counts, references,
  960 reservations/terminal settlements and **1,920 identical PG/JSONL events**. Each of the 960 requests
  records `MOCK_SYNTHETIC_V1`, `MOCK_NOT_BILLABLE`, null billed amount and cost NOT_RUN.
* Timeout and malformed-response smoke trials each retain four failed and sixteen completed turns, return 1,
  and account for all 52 attempted requests. A four-call budget trial retains four failed and sixteen MISSING
  turns, eight attempted requests (four refused before reservation), four reservations/terminal settlements,
  zero pending and four durable budget-stop reasons. None is converted into a complete trial.
* A discovered failure-accounting omission and an independent verifier's initial failure to count charged
  `failed` terminal events were fixed. Old failing trial/verification records remain unchanged. The metadata
  test initially failed for buffered Mock responses; the owned full-run supervisor was identity-checked,
  cancelled and awaited to CANCELLED/cleanup complete. Its partial artifacts and tooling commit remain.
* Both final blind packets were exported and imported with **zero completed annotations**. A has 100 distinct
  assignments (75 development / 25 holdout); B has 20 overlapping independent assignments. Independent
  verification confirms 20 strata × five primary samples. Scores remain null/NOT_RUN, with zero comparable
  model/human and double-annotation pairs. No human labels were generated from the Mock reviews.
* Arithmetic checks use only hand-constructed fixtures: pair support 1/3, presence coverage 2/3, supported
  coverage 1/3; agreement .75 and kappa .5 on four comparable binary pairs. These are test expectations,
  **not observed Tutor or human quality**. Unknown/uncertain/degenerate cases and missing assignments are tested.
* All five generated data/manifest files reproduce byte-for-byte from original author sources in an empty
  scratch location. Dataset, holdout and original P8 pins verify; original P8 summary fields also recompute
  identically from its original raw dialogue/review files, without changing any historical verdict.
* Ruff lint/format pass. All 18 completed network records observed zero denied connection attempts; the
  final Mock path used only fake transport and its own loopback PG. No provider credential was read.

## Local artifacts and stop state

All paths below are relative to the independent workspace, not the protected source checkout:

| Artifact | Location |
| --- | --- |
| Final full configuration, raw turns, per-course calls/ledgers/accounting | `.data/tutor-scale/full-verified-final-20261107/` |
| Final 100/20 packets, empty imports, null scores, private identity map | `.data/tutor-scale/blind-verified-final-20261107/` |
| Independent full and smoke reconciliation | `.data/tutor-scale/{full,smoke}-independent-verification.json` |
| Three fault trials and independent reconciliation | `.data/tutor-scale/fault-validation-final.json` and `*-terminal-final-20261107/` |
| Test XML, source reconstruction, history and preservation checks | `.data/tutor-scale/` |
| Owned process terminal records and logs | `.data/dev-checks/` |
| Earlier failed/cancelled trials and manifest snapshots | `.data/tutor-scale/` and `candidate-history/` |

All supervised checks have terminal records; cleanup is complete. The newly created PostgreSQL container is
**stopped**, its volume retained. No other container was stopped. Final resource checks remained about 13 GiB
available RAM and 44 GiB free disk. The protected checkout still has its original branch, HEAD and six dirty
entries. Product code, historical P8/P7/AU assets and CI are unchanged. Nothing was pushed, deployed or submitted
as a PR.

Preparation has no remaining execution blocker. Independent people have not annotated packets and no current
pricing/billing basis was validated; both are prerequisites to future real claims. Real citation accuracy,
real model/human consistency, real tokens/cost, natural-course generalization and learning effects remain
**NOT_RUN**. This task stops at local commits and does not authorize a real trial.
