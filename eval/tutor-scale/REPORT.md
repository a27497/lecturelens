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

Final verification details and artifact hashes are recorded after executing the frozen tooling commit.
