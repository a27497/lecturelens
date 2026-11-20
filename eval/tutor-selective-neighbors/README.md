# Selective neighbors for Light Tutor

Selective neighbors covered every required nugget on **20/24** frozen L4 dev questions, up from **18/24** on main (#86). Expanding every query covered **19/24**. Selective kept cross-segment full coverage at **3/3**, compared with **2/3** for expanding every query. Average evidence grew from **10,400.73 to 14,482.13 UTF-8 bytes** across all 30 questions. The six refusal items accounted for the largest proportional increase, from **7,403.50 to 14,610.17 bytes** on average. The replay measured Evidence coverage and context size. It used no model calls and consumed no new holdout.

## First-pass retrieval

Every arm used the #86 query plan. All 30 main records matched the historical #86 per-item replay. Selective matched main on the 12 split questions and matched all-query expansion on the 18 unsplit questions. Selective gained two fully covered questions and lost none versus main. All-query expansion gained two and lost one. Both used at most 16 distinct Evidence excerpts after authoritative READ.

Each coverage cell gives fully covered questions / answerable questions, then covered vital nuggets / vital nuggets. Cross-segment full coverage is the full-question measure for that category.

| Frozen category | Main (#86) | All queries + neighbors | Selective |
| --- | ---: | ---: | ---: |
| Definition or fact | 5/6 · 10/12 | 6/6 · 12/12 | 6/6 · 12/12 |
| Explanation | 4/6 · 5/9 | 5/6 · 8/9 | 5/6 · 8/9 |
| Procedure or worked example | 4/6 · 10/15 | 4/6 · 12/15 | 4/6 · 12/15 |
| Comparison | 2/3 · 5/6 | 2/3 · 5/6 | 2/3 · 5/6 |
| Cross-segment | 3/3 · 7/7 | 2/3 · 6/7 | 3/3 · 7/7 |
| **All answerable** | **18/24 · 37/49** | **19/24 · 43/49** | **20/24 · 44/49** |

Context cells give mean / nearest-rank P95 UTF-8 bytes of the exact evidence array. Refusal rows report context only.

| Frozen category | Questions | Main (#86) | All queries + neighbors | Selective |
| --- | ---: | ---: | ---: | ---: |
| Definition or fact | 6 | 12,499.17 / 16,439 | 14,855.33 / 16,568 | 14,690.67 / 16,439 |
| Explanation | 6 | 8,737.17 / 14,172 | 14,454.17 / 16,369 | 14,334.33 / 16,369 |
| Procedure or worked example | 6 | 8,382.00 / 14,625 | 13,763.33 / 14,886 | 13,793.67 / 14,886 |
| Comparison | 3 | 15,000.67 / 17,067 | 15,007.67 / 16,674 | 15,000.67 / 17,067 |
| Cross-segment | 3 | 14,963.00 / 16,354 | 15,128.00 / 15,903 | 14,963.00 / 16,354 |
| **All answerable** | **24** | **11,150.04 / 16,439** | **14,535.17 / 16,568** | **14,450.12 / 16,439** |
| Refusal · near miss | 3 | 7,196.00 / 8,164 | 14,552.33 / 15,809 | 14,552.33 / 15,809 |
| Refusal · unsupported detail | 3 | 7,611.00 / 8,362 | 14,668.00 / 16,342 | 14,668.00 / 16,342 |
| **All refusal items** | **6** | **7,403.50 / 8,362** | **14,610.17 / 16,342** | **14,610.17 / 16,342** |
| **All items** | **30** | **10,400.73 / 16,439** | **14,550.17 / 16,568** | **14,482.13 / 16,439** |

| Reproduction identity | SHA-256 |
| --- | --- |
| [Preregistered rules](PREREGISTRATION.md) | `8ee0a46af701f431cb0d7f4691902bb0c1eb76cb938f8ed4c068ea73d10a9831` |
| Frozen dev questions | `5b8969ec75a410fb2fcc843636cf2443540ec91d7449004908310a7185489bdd` |
| Original support mapping | `510fbb48c7018c6129c2ceb89f51130ef42b47b0c78b4d66963e0effba9528af` |
| Canonical Evidence snapshot, 356 published excerpts | `a900b6915ead8d2935ca260879718dff20296731c5651f756d1f520759d8e4b6` |
| Ordered index manifest, 1,006 chunks | `bb7fa578acdfcd89f0668bae4221426cb775c5d65eda0b87b0201227fe12cb4e` |
| First-pass per-item receipts | `ef1f76e5e42c73e09113a258cdb57cb49e3d746f70bd959ef20fe90a87b15d99` |
| First-pass aggregates | `6ad45c0d116404cb288021412f68ad3ade15902f0cda70c3e45beab83ae0f020` |

The first-pass source was `c9b12d99c05650127334a829a31e66f9510fc23f`. The review follow-up added a live index fence with synthetic verification. The original run recorded the index build receipt and matched all historical main-arm cases. Its per-response snapshot identities were unrecorded. A subsequent read-only audit confirmed the three expected snapshots, Evidence hashes and ordered chunk manifest in the task database. The first-pass files and rules fingerprint remain the run of record.

For reproduction, use the [signed retrieval fixture setup](../tutor-retrieval-dev/README.md#reproduction) with an isolated `lecturelens_agent_test` database, two unused loopback ports, a new shared signing key and the existing offline embedding cache. Capture the final JSON line from `tutor_retrieval_dev.py index` as the index receipt. With the same vector environment and shared signing key exported, run the locked vector fixture from the repository root:

```bash
umask 077
agent-service/.venv/bin/python scripts/eval/tutor_selective_neighbors.py serve-vector \
  "$L4_DEV_ROOT" "$ORIGINAL_SUPPORT_JSON" "$INDEX_RECEIPT_JSON" \
  "$VECTOR_FIXTURE_PORT" "$NEW_VECTOR_RECEIPT_JSONL"
```

Start the Java fixture with that vector port and its own loopback port. With the signing key exported, run:

```bash
umask 077
agent-service/.venv/bin/python scripts/eval/tutor_selective_neighbors.py score \
  "$L4_DEV_ROOT" "$ORIGINAL_SUPPORT_JSON" "$INDEX_RECEIPT_JSON" \
  "$JAVA_FIXTURE_PORT" "$NEW_VECTOR_RECEIPT_JSONL" "$NEW_PRIVATE_OUTPUT_DIR"
```

The vector fixture checks the embedding version and the expected course snapshot identity on each live dense response. The scorer checks the received page identities and count for each arm and writes `cases.jsonl` and `aggregates.json`. Its output directory must be new. It records each item's query-plan digest, vector snapshot identity and final Evidence IDs in the private receipt.

## Two-case Flash judge calibration

The [versioned Flash judge](../../agent-service/src/lecturelens_real_eval/l4/flash_judge.py) asks the grader to group substantive assertions into at most six entries while keeping unsupported assertions and material errors. A group earns full citation support only when every constituent assertion has full support from its attached excerpts. The validator still rejects oversized claim lists and invalid citation support. The scorer derives the verdict from answerability, the declared-insufficiency flag, the vital-nugget labels and the material-error flag. The explicit unreadable flag retains the original undetermined outcome. Strict correctness requires full support for every vital nugget and no material error. The judge reports citation quality separately. Synthetic checks compare the derived verdict with the existing L4 validator.

The replay used the original normalized Tutor answers, citations and rubric from the two still-invalid cases. It rebuilt each original request and matched its hash and Tutor-answer hash against the historical receipts, then replaced the system message under `l4-flash-judge-v1`. The user message bytes matched the prior requests. The prompt SHA-256 is `25bd2268aec4c1fd17963b406ca955ac4db1352ef6ae805c3796d5b9a72d65a7`. One request per case used the `deepseek-flash` Chat Completions route (DeepSeek-V4.1-Flash-1017), thinking disabled, a 4,096-output-token cap and zero retries. Both raw responses were saved privately before parsing. [Official CNY pricing and routing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing), [Chat Completions contract](https://api-docs.deepseek.com/api/create-chat-completion).

| Case | Prior invalidity | New status | Cache-hit / cache-miss / output tokens | CNY charge |
| --- | --- | --- | ---: | ---: |
| 1 · Explanation | Verdict conflicted with vital labels | Invalid. The response followed the derived-verdict format and marked an uncited claim as supported. No valid correctness judgment. | 0 / 2,270 / 437 | ¥0.00401800 |
| 4 · Cross-segment | More than six claims | Valid and strictly correct. Five claim entries. | 512 / 1,940 / 564 | ¥0.00420624 |
| **Total** | | | **512 / 4,210 / 1,001** | **¥0.00822424** |

On the 24 historical answerable responses, counting invalid judgments as failures, the two replacements move the calibration tally from **20/24 to 21/24**. This is a judgment update for the old Tutor answers. The selective retrieval arm has no end-to-end correctness score.

For an authorized judge replay, build each verified historical entry with `flash_judge.request_body`, serialize with `l4.blind.canonical`, and reserve the uncached input upper bound (serialized UTF-8 bytes plus 256 framing tokens) and the full output cap at peak prices. The two reservations totaled **¥0.107572** against the **¥0.5** cap. Use a persistent per-case reservation before the POST, count unresolved requests at their full reservation, and settle valid usage at the rate in effect. Write the raw body to a new 0600 file in a 0700 directory before JSON decoding and apply `flash_judge.validate` only to a completed Flash response. Both requests ran off peak and returned usage. Uncertain exposure was ¥0. The charges use provider-reported token usage and the published rates. An account invoice was unavailable. [Official CNY pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing).

| Case | Request SHA-256 | Raw response SHA-256 |
| --- | --- | --- |
| 1 | `7f701a6517f4aa4be34eb27668cb44bbb920e58bd8d06c43c8fca34ec97720a2` | `4cb53849a901e68d093a85c4189ba7403550dfd653fdaed1d9cbeaad33f729fc` |
| 4 | `b2cdaec7d94d7abf2e9e9348640313069ce385f83f5118dff82c2c85d472df04` | `2f99a3234806cc3da97ccab3022bf118cf21793ec1fea7ba0239abd3ef9edecb` |

The private charge ledger SHA-256 is `42703a43826e9fbec82643c445663c1bde96d07121f06cddd8349301d4ae1d2d`.
