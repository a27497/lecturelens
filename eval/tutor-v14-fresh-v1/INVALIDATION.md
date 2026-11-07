# Invalid preparation — do not dispatch this bundle

The first guarded startup failed with `V14_SOURCE_CHANGED` before pytest
collection, any runtime/ledger installation or any credential consumption.
No real model/embedding/reviewer request occurred. The user requires stopping on
a preflight failure, so this batch ends here without repair or another attempt.

During preparation, the assistant ran directory-wide `ruff format` over this
bundle. It changed Python code fences in the downloaded `05-loop.md`, including
single to double quotes and exponent spacing. The source record still pins the
original downloaded bytes; startup correctly rejects the inconsistency. The
spreadsheet episode and both licenses still match their recorded source hashes.
The freeze-lock itself matches all of its files: source-byte verification is a
separate check and must not be bypassed or satisfied by replacing old hashes.

| Python source | SHA-256 |
| --- | --- |
| Pinned download / expected | `59ad81e33ec8881f3a8bafb8f220ec5b9bea8af6e9caee7fbdefffaa703ffc53` |
| Prepared formatted copy / observed | `dd472a2a972b5b25a24b120a9da4ce8a79cdd3e3df89ace7e62873894c02c206` |

The original 10,863-byte download and the diff against the 10,861-byte prepared
copy are retained privately as `python-original-source.md` and
`python-source-diff.patch` under `.data/tutor-v14-real-20261107/`. No frozen
source, reference, hash, threshold or failed log was changed after detection.

This additive entry and its new 17 tests are **UNVALIDATED**. The earlier v14
runtime's 219-pass offline evidence remains unchanged; it does not validate this
new entry. No candidate output was seen on the16 new positions. A later repair,
replacement freeze or paid dispatch requires a new explicit instruction; nothing
in the existing `execution_authorized` metadata carries permission forward.

For any separately authorized future preparation, format only explicitly listed
Python implementation/test files, retain immutable downloaded source bytes, and
verify source hashes before freezing references. That is a recommendation, not a
repair applied to this invalid bundle.
