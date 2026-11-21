# LL-P16 paired Tutor holdout

B increased strict correctness from **30/48 to 33/48**, a difference of **+6.25 percentage points**. The paired 95% interval **[−2.08, +14.58]** includes zero, so the increase lacks statistical significance at the 95% level. Complete vital coverage improved from **6/48 to 12/48**, or **+12.50 points** with a paired 95% interval **[+4.17, +20.83]** that excludes zero. On cross-segment items, complete coverage remained **0/9** in both arms and strict correctness fell from **4/9 to 3/9**. Both arms correctly refused **11/12** required-refusal items. These estimates describe six lectures drawn from two course releases.

A uses the #86 hybrid retrieval policy. B uses the combined #87/#88 main base and adds neighbors on unsplit queries. Both arms used the same approved questions, Evidence, non-thinking DeepSeek Flash model, Tutor prompt and Flash v1 judge. The experiment included one scheduled turn per arm for each of 60 items. The immutable specification and hashes are in the freeze. The full unrounded results include all eight reporting populations, every frozen paired interval, raw denominators and defined bootstrap draw counts. [Freeze PR #89](https://github.com/a27497/lecturelens/pull/89) · [Exact frozen file](https://github.com/a27497/lecturelens/blob/eff47169f4f6d861458ca8b318e8fd5c11bc1ec6/eval/ll-p16-holdout/freeze.json) · [Aggregate JSON](results.json)

## Automatic results

| Metric | A | B | B−A, percentage points [paired 95% CI] |
| --- | ---: | ---: | ---: |
| Strict correctness | 30/48 (62.50%) | 33/48 (68.75%) | +6.25 [-2.08, +14.58] |
| Required-refusal accuracy | 11/12 (91.67%) | 11/12 (91.67%) | +0.00 [-25.00, +25.00] |
| Complete vital coverage | 6/48 (12.50%) | 12/48 (25.00%) | +12.50 [+4.17, +20.83] |
| Micro vital coverage | 17/93 (18.28%) | 30/93 (32.26%) | +13.98 [+8.33, +19.79] |
| Material error among assessed answerable answers | 0/35 (0.00%) | 1/38 (2.63%) | +2.63 [+0.00, +7.89] |

Strict correctness requires a valid judgment, an actual answer, all vital nuggets supported and no material error. Required-refusal accuracy requires declared insufficiency with a valid judgment and no material error or unsupported teaching. Delivery failures and terminal invalid judgments earn zero in their scheduled endpoint. Each arm has 48 strict and 12 refusal slots. Coverage uses the original conjunctive alternatives over the 93 vital nuggets and the ordered, authoritative Evidence prepared offline.

| Item type | Endpoint | A | B | B−A, pp [95% CI] | Complete vital A → B | B−A, pp [95% CI] | Micro vital A → B | B−A, pp [95% CI] |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Definition or fact | Strict | 6/10 (60.00%) | 9/10 (90.00%) | +30.00 [+10.00, +60.00] | 1/10 → 3/10 | +20.00 [+0.00, +40.00] | 3/13 → 5/13 | +15.38 [+0.00, +33.33] |
| Explanation | Strict | 7/10 (70.00%) | 8/10 (80.00%) | +10.00 [+0.00, +30.00] | 2/10 → 5/10 | +30.00 [+0.00, +60.00] | 5/17 → 12/17 | +41.18 [+18.75, +62.50] |
| Procedure or worked example | Strict | 8/10 (80.00%) | 7/10 (70.00%) | -10.00 [-30.00, +0.00] | 2/10 → 3/10 | +10.00 [+0.00, +30.00] | 5/22 → 7/22 | +9.09 [+0.00, +19.05] |
| Comparison | Strict | 5/9 (55.56%) | 6/9 (66.67%) | +11.11 [+0.00, +33.33] | 1/9 → 1/9 | +0.00 [+0.00, +0.00] | 3/18 → 4/18 | +5.56 [+0.00, +16.67] |
| Cross-segment | Strict | 4/9 (44.44%) | 3/9 (33.33%) | -11.11 [-33.33, +0.00] | 0/9 → 0/9 | +0.00 [+0.00, +0.00] | 1/23 → 2/23 | +4.35 [+0.00, +14.29] |
| Near miss | Refusal | 6/6 (100.00%) | 6/6 (100.00%) | +0.00 [+0.00, +0.00] | — | — | — | — |
| Omitted detail | Refusal | 5/6 (83.33%) | 5/6 (83.33%) | +0.00 [-50.00, +50.00] | — | — | — | — |

### Paired discordances and support coverage

Seven answerable pairs differed on strict correctness. Three had byte-identical ordered Evidence and identical Tutor request hashes. A was correct in two of those pairs and B in one. Generation or judging variability is compatible with those records. The other four pairs had different Evidence membership, and B was correct in all four. This observed paired pattern leaves the causal contribution of retrieval undetermined.

Complete coverage is strict against the preregistered gold support. Each vital nugget needs every fragment in at least one approved alternative. For an item, the minimum fragment count is the smallest distinct union obtained by choosing one approved alternative per vital nugget. That minimum was **2–7 fragments for 40/48** answerable items, **1 fragment for 4/48**, and **8, 9, 10 or 12 fragments for 4/48** (one each). Across the **93 vital nuggets**, 83 had a smallest alternative of 2–7 fragments and 10 had a smallest alternative of one. The nine cross-segment items required a minimum of **4–8** distinct fragments each. Both arms capped prepared context at **16 distinct fragments** and reached that cap in the recorded round. The cap limits how many fragments fit, while coverage depends on which fragments retrieval selects. Models can answer well-known course concepts from prior knowledge. Exact frozen support coverage alone cannot establish grounding or identify the source of any particular answer.

## Prepared Evidence size

Sizes use the frozen canonical UTF-8 array of ordered authoritative Evidence, including row metadata. All 120 contexts were ready. The 95th percentile is nearest rank. Paired intervals recompute the statistic in each draw.

| Population | Mean A | Mean B | Mean B−A [95% CI] | P95 A | P95 B | P95 B−A [95% CI] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All 60 | 3,883.03 | 5,717.72 | 1,834.68 [1,528.88, 2,129.42] | 6,799 | 6,853 | 54 [0, 310] |
| Answerable 48 | 3,818.52 | 5,691.29 | 1,872.77 [1,534.17, 2,192.58] | 6,806 | 6,853 | 47 [0, 249] |
| Required refusal 12 | 4,141.08 | 5,823.42 | 1,682.33 [904.58, 2,427.33] | 6,568 | 7,004 | 436 [23, 1,765] |
| Definition or fact | 3,653.30 | 5,513.40 | 1,860.10 [1,025.20, 2,494.00] | 6,650 | 6,650 | 0 [0, 1,493] |
| Explanation | 3,287.50 | 5,823.70 | 2,536.20 [1,868.80, 2,964.60] | 6,806 | 6,853 | 47 [0, 3,517] |
| Procedure or worked example | 3,680.00 | 5,541.80 | 1,861.80 [1,071.70, 2,522.10] | 6,868 | 6,868 | 0 [0, 1,327] |
| Comparison | 3,691.44 | 5,826.11 | 2,134.67 [1,442.56, 2,811.44] | 6,799 | 6,799 | 0 [0, 2,935] |
| Cross-segment | 4,873.11 | 5,773.11 | 900.00 [262.89, 1,800.00] | 7,056 | 7,056 | 0 [0, 162] |
| Near miss | 4,319.83 | 5,761.67 | 1,441.83 [406.67, 2,411.50] | 6,543 | 6,591 | 48 [0, 1,407] |
| Omitted detail | 3,962.33 | 5,885.17 | 1,922.83 [784.33, 2,915.33] | 6,568 | 7,004 | 436 [0, 3,425] |

Paired 95% intervals use 10,000 bootstrap draws with the pair held together and the observed course-by-type composition fixed. The seed is 161707. Endpoints are the nearest-rank 2.5th and 97.5th percentiles of defined differences. The intervals are per metric and reflect variation among items within these course releases.

## Failure and grading accounting

| Arm and scheduled endpoint | Answered | Declared insufficient | Product failure | Valid judgment | Repeat invalid | No judge request |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A, answerable (48) | 37 | 9 | 2 | 44 | 2 | 2 |
| A, required refusal (12) | 0 | 11 | 1 | 11 | 0 | 1 |
| B, answerable (48) | 40 | 4 | 4 | 42 | 2 | 4 |
| B, required refusal (12) | 0 | 11 | 1 | 11 | 0 | 1 |

Tutor protocol/output-format failures totaled **3 for A and 5 for B**. All eight remain among the 120 scheduled outcomes. Two affected A's strict denominator and four affected B's. One affected each required-refusal denominator. Among 112 initial judgments, 17 were invalid and retried once. Sixteen initially failed the citation-support schema and one had malformed JSON. Thirteen retries produced valid judgments. All four terminal invalids failed the citation-support schema, leaving two incorrect strict slots in each arm. They were charged and remain in the automatic counts. No refusal slot was repeat-invalid.

Material error uses the 35 assessed answers in A and the 38 in B. Two delivered answerable answers per arm were unassessed because of repeat-invalid judgments. Counting those answers as clean or erroneous in turn bounds the rates at **0.00%–5.41% for A** and **2.50%–7.50% for B**. The strict denominators continue to include all 48 scheduled answerable slots per arm.

## Independent blind audit

The signed audit covered all 30 anonymous responses from the frozen 15 pairs, including three failed deliveries. No binary endpoints were undetermined. All 14 course-by-type strata were represented. Thirteen strata supplied one pair and one supplied two. The aggregate file records the inclusion probability for each stratum under neutral course labels.

| Endpoint | Arm | Agreement | Cohen’s κ | False accept | False reject | Net false acceptance |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Strict | A | 10/11 (90.91%) | 0.814 | 0 | 1 | -1/11 (-9.09%) |
| Strict | B | 10/11 (90.91%) | 0.820 | 0 | 1 | -1/11 (-9.09%) |
| Refusal | A | 4/4 (100.00%) | Undefined | 0 | 0 | +0/4 (+0.00%) |
| Refusal | B | 4/4 (100.00%) | Undefined | 0 | 0 | +0/4 (+0.00%) |

The audit found one strict disagreement per arm, both false rejections, and no refusal disagreements. The sampled refusal labels were constant within each arm, so κ is undefined.

As a secondary exploratory check, the design-weighted correction adds the reviewer-minus-automatic delta weighted by stratum population divided by sample size, then divides by the applicable endpoint population. The strict adjustment was **+10.42 points** per arm, giving **72.92% for A** and **79.17% for B** and a paired difference of **+6.25 points**. The refusal estimate was **91.67%** per arm, with a **0.00-point** adjustment and paired difference. These point estimates have limited precision with one or two audited pairs per stratum and four refusal pairs overall.

## Future use

All **60 items are SEEN** for future work. They are for diagnostics and regression checks only. Exclude them from future tuning, candidate selection, and official scores.

## Usage ledger and provenance

| Stage | Dispatches | Cache-hit input tokens | Cache-miss input tokens | Output tokens | Settled CNY | Unresolved CNY |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tutor | 120 | 114,688 | 141,352 | 41,866 | 0.311109760 | 0.000000000 |
| Initial judge | 112 | 84,480 | 104,419 | 32,162 | 0.234756600 | 0.000000000 |
| Conditional judge retry | 17 | 30,459 | 3,360 | 7,071 | 0.032253180 | 0.000000000 |
| Total | 249 | 229,627 | 249,131 | 81,099 | 0.578119540 | 0.000000000 |

All 249 dispatches used the frozen off-peak rates of CNY 0.02 per million cache-hit input tokens, CNY 1 per million cache-miss input tokens and CNY 4 per million output tokens. The declared reservation bound was CNY 9.97824 under a CNY 10 hard cap. The ledger includes paid invalid responses and both judge attempts when applicable. [Official CNY rates](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

| Binding | Identity |
| --- | --- |
| Freeze commit | `eff47169f4f6d861458ca8b318e8fd5c11bc1ec6` |
| Freeze file SHA-256 | `7a974ae682781668ac36c293de07364c21905d3f42aba35904ab2eba96510980` |
| Freeze Git blob | `187c75096211f9abc5f56a8cbe1e75402c262dca` |
| A | `ef6fcd2b9fc566df92cb7f98fc98de561e911737` |
| B | `7964a2482e17f84e0373df7afc7c8179450dbc0c` |
| Tutor prompt SHA-256 | `509927cb92eccdbe8d17b5a6eee38d1e8b486ab3d48567fbec94dc56adab443c` |
| Judge build SHA-256 | `7b0e06dba60f2f2952f14ce47be135a86d6602f309e5737e90ef8a6009208e59` |
| Judge prompt SHA-256 | `25bd2268aec4c1fd17963b406ca955ac4db1352ef6ae805c3796d5b9a72d65a7` |
| Model and judge | `deepseek-flash / DeepSeek-V4.1-Flash-1017`, `l4-flash-judge-v1` |
| Observed backend fingerprint SHA-256 | `1a6803ba5e0151269dd7176cb9da9b01ddc13059acade5106bb15242125325b0` |
| Material receipt SHA-256 | `846682b1ef642b57cf2fb02b2c7491d552b90ce98c5b62ea2b5a8267e37c193a` |
| Sealed run data SHA-256 | `d1ceddb18229188235c677b448f1df781253eb73d26f9d898261ba0975757035` |
| Signed blind audit SHA-256 | `8955133f86efe4b9acbaf373eab34c852906791363121eb0fa5f8e459abaab07` |
| Published aggregate JSON SHA-256 | `2272fe1e0c26eb935723b56079f36c13cd5909534306ee793dfb54b2d96ba195` |

## Verification

The frozen unblinding run reproduced the original aggregate data and paired intervals. Read-only validation independently recalculated the point estimates and denominators in eight populations, the signed sample's agreement and design-weighted corrections, and the charges for all 249 reservations. It reproduced the signed sample membership, confirmed all four terminal invalids earned zero, and checked that the publication contains aggregates and digests only. The pinned harness and final schema adapter passed 83 synthetic and regression tests. This report adds no product or holdout execution changes.
