# Light Tutor retrieval on L4 development data

The selected configuration covered every vital nugget for **18/24** answerable questions on the existing 30-item L4 development set. The main-branch Tutor context covered **14/24**. Comparison coverage rose from **0/3 to 2/3**, and cross-segment coverage rose from **2/3 to 3/3**.

The historical L4 Tutor strict-correct score was 155/216 answerable attempts. The old 96 questions are **PREVIOUSLY INSPECTED — regression reference only**. The previously reported diagnostic saw all vital nuggets retrieved for 62.5% of attempts, about 86% correctness when all were retrieved, about 48% when one was missing, and 13/36 strict cross-segment answers. Those historical numbers motivated this work. The dev coverage metric below uses final input excerpts, 24 unique answerable questions, and an explicit support-group crosswalk. The old questions and output records were outside the replay.

## Offline scoring and paid-run gate

Each existing dev vital nugget has one or more independently sufficient Evidence groups. Every ID in a group must occur in the final `current_evidence` array, after deduplication and authoritative READ. The scorer checks whether all of a question's vital nuggets are covered and counts covered vital nuggets separately. The support crosswalk uses the frozen caption cues to locate whole published excerpts and checks which facets need multiple excerpts together. Same-interval translations were accepted as alternatives where they preserve the necessary content. Six should-abstain questions, three related-topic near misses and three unsupported details, are excluded from both coverage denominators. Their retrieval costs are shown separately.

The gate was recorded before candidate replay. A candidate needed at least two more fully covered answerable questions than main, with no drop on either comparisons or cross-segment questions and a cap of 16 distinct excerpts. Main uses the signed Java SEARCH path, which retrieves four dense anchors and fills adjacent context up to eight. Single-query dense Top 8 is also reported. All strategies use the same 356 published excerpts, 1,006 production embedding chunks, frozen MiniLM revision and PostgreSQL cosine ranking. The development gate applies to this one paid batch.

Each cell gives **fully covered questions / covered vital nuggets**, with both denominators shown.

| Configuration | All answerable | Definition | Explanation | Procedure | Comparison | Cross-segment |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Main dense 4 + neighbors | 14/24 / 33/49 | 5/6 / 11/12 | 4/6 / 5/9 | 3/6 / 8/15 | 0/3 / 3/6 | 2/3 / 6/7 |
| Dense 8 | 9/24 / 23/49 | 3/6 / 7/12 | 3/6 / 5/9 | 2/6 / 6/15 | 1/3 / 4/6 | 0/3 / 1/7 |
| Hybrid 8 | 12/24 / 28/49 | 3/6 / 7/12 | 3/6 / 4/9 | 4/6 / 10/15 | 2/3 / 5/6 | 0/3 / 2/7 |
| Hybrid 16 | 18/24 / 41/49 | 5/6 / 11/12 | 5/6 / 8/9 | 4/6 / 11/15 | 2/3 / 5/6 | 2/3 / 6/7 |
| Hybrid 8 + neighbors | 19/24 / 43/49 | 6/6 / 12/12 | 5/6 / 8/9 | 4/6 / 12/15 | 2/3 / 5/6 | 2/3 / 6/7 |
| Routed hybrid 8 | 14/24 / 32/49 | 4/6 / 9/12 | 4/6 / 5/9 | 4/6 / 10/15 | 2/3 / 5/6 | 0/3 / 3/7 |
| Routed hybrid 16 (selected) | 18/24 / 37/49 | 5/6 / 10/12 | 4/6 / 5/9 | 4/6 / 10/15 | 2/3 / 5/6 | 3/3 / 7/7 |
| Routed hybrid 8 + neighbors | 17/24 / 36/49 | 5/6 / 10/12 | 4/6 / 5/9 | 4/6 / 10/15 | 2/3 / 5/6 | 2/3 / 6/7 |

Excerpt and byte columns give mean / nearest-rank P95 / maximum over all 30 items. UTF-8 bytes of the exact serialized evidence array provide a conservative upper-bound token proxy and exclude instructions, dialogue, questions and generation. The last two columns cover only the six should-abstain items. Their coverage score is inapplicable.

| Configuration | Excerpts | UTF-8 bytes | Mean vs. main / dense 8 | Refusal items, excerpt mean / max | Refusal items, byte mean / max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Main dense 4 + neighbors | 7.37 / 8.00 / 8.00 | 6,876 / 8,584 / 8,601 | 1.00× / 0.97× | 7.00 / 8 | 6,603 / 8,318 |
| Dense 8 | 8.00 / 8.00 / 8.00 | 7,116 / 8,512 / 8,528 | 1.03× / 1.00× | 8.00 / 8 | 7,128 / 8,512 |
| Hybrid 8 | 8.00 / 8.00 / 8.00 | 7,486 / 8,503 / 8,644 | 1.09× / 1.05× | 8.00 / 8 | 7,404 / 8,362 |
| Hybrid 16 | 16.00 / 16.00 / 16.00 | 14,932 / 16,608 / 17,173 | 2.17× / 2.10× | 16.00 / 16 | 14,981 / 16,591 |
| Hybrid 8 + neighbors | 15.47 / 16.00 / 16.00 | 14,381 / 16,369 / 16,674 | 2.09× / 2.02× | 15.67 / 16 | 14,610 / 16,342 |
| Routed hybrid 8 | 10.67 / 16.00 / 16.00 | 9,975 / 16,429 / 16,471 | 1.45× / 1.40× | 8.00 / 8 | 7,404 / 8,362 |
| Routed hybrid 16 (selected) | 11.20 / 16.00 / 16.00 | 10,401 / 16,439 / 17,067 | 1.51× / 1.46× | 8.00 / 8 | 7,404 / 8,362 |
| Routed hybrid 8 + neighbors | 11.20 / 16.00 / 16.00 | 10,469 / 16,568 / 16,674 | 1.52× / 1.47× | 8.00 / 8 | 7,404 / 8,362 |

The product keeps a single hybrid Top 8 query for simple first turns and uses hybrid Top 16 per focused query for comparisons and questions with distinct parts. The route detected all six comparison and cross-segment items plus six other multipart items without question IDs or gold. Reciprocal rank fusion caps the final context at 16. Single-query hybrid 8 plus neighbors covered one more question overall, used 38% more context bytes than the selected route, and covered one fewer cross-segment question. The routed variants use the same simple path. Each hybrid query requests at most two local dense pages within the existing eight-hit wire limit. The selected routed variant led the other routed variants in full coverage and cross-segment coverage.

## Reproduction

Use [the dev replay](../../scripts/eval/tutor_retrieval_dev.py) with the authorized frozen L4 dev directory, a private support-group mapping, a separate `lecturelens_agent_test` database, an existing MiniLM cache, and two unused loopback ports. The `index` subcommand rebuilds only the dev projection with `HF_HUB_OFFLINE=1`. It emits the canonical Java fixture from the three source snapshots. Run `serve-vector` on one port and compile and launch [the Java fixture](../../backend/src/test/java/com/example/courselingo/study/TutorDevEvidenceServer.java) on the other. Give both the same ephemeral `TUTOR_DEV_SIGNING_KEY`. The fixture takes the snapshot file, its listen port and the vector port. The production signed controller, Evidence authority, dense client, embedding code, PostgreSQL search and Light Tutor context are exercised. The Java data layer uses isolated H2 task rows and a frozen Evidence fixture. Run `score baseline` and then `score candidate` against the fixture. Each writes private per-item results to a new file and prints aggregates. The support mapping format is question ID → vital nugget ID → list of alternative lists of sufficient Evidence IDs.

| Input | SHA-256 |
| --- | --- |
| Frozen dev question packet | `5b8969ec75a410fb2fcc843636cf2443540ec91d7449004908310a7185489bdd` |
| Canonical Evidence snapshot | `a900b6915ead8d2935ca260879718dff20296731c5651f756d1f520759d8e4b6` |
| Ordered chunk manifest | `bb7fa578acdfcd89f0668bae4221426cb775c5d65eda0b87b0201227fe12cb4e` |
| Private support crosswalk | `510fbb48c7018c6129c2ceb89f51130ef42b47b0c78b4d66963e0effba9528af` |
| Preregistered offline plan | `c33c9d3d451852ce8cdfcb2c0df9f3cf2799a2837484a28eec2c62876c96877e` |

Historical benchmark reproduction uses its original source revision and [published freeze record](../l4-benchmark/freeze.json). This dev set was used to select the configuration. A new holdout would be needed to evaluate generalization.
