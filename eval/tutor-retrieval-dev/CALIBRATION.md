# Light Tutor routing and Flash calibration on L4 development data

The four authorized Flash judgment replays raised the historical Tutor score from **18/24 to 20/24**. The Tutor answers were generated in the previous batch. This change to their score measures the effect of replaying invalid judgments.

The submitted Light Tutor route lowered mean answerable context bytes by **22.0%** and mean query count from **2.00 to 1.33**. Full vital coverage fell from **18/24 to 12/24**. A matched alternative with hybrid Top 8 plus neighbors reached **19/24**, with about **66%** more answerable context bytes than the submitted route. Neighbor expansion remains an offline comparator.

Only the existing 30 L4 development items, their frozen Evidence and support groups, and the previous paid Tutor answers were used. The old 96 items are **PREVIOUSLY INSPECTED** historical reference. No new formal test set was prepared, frozen, or run.

## Judgment replay and spend

Each of the four original invalid judgments was attempted exactly once. All four reconstructed requests matched their historical wire digests. The calls used the original L4 rubric and validator, the official `deepseek-flash` alias for DeepSeek-V4.1-Flash-1017, explicit disabled thinking, and the original 4,096-token output cap. All four responses reported the requested model and parsed as JSON. The validator accepted two responses. It rejected one for exceeding the claim list limit and one for a verdict inconsistent with its vital-nugget labels. The two invalid judgments count as incorrect within the same denominator of 24.

| Question type | Original strict correct | After replay | Increase | Still invalid |
| --- | ---: | ---: | ---: | ---: |
| Definition | 5/6 | 5/6 | 0 | 0 |
| Explanation | 4/6 | 4/6 | 0 | 1 |
| Procedure | 6/6 | 6/6 | 0 | 0 |
| Comparison | 2/3 | 3/3 | +1 | 0 |
| Cross-segment | 1/3 | 2/3 | +1 | 1 |
| **Answerable** | **18/24 (75.0%)** | **20/24 (83.3%)** | **+2** | **2** |

The historical refusal result remains **5/6**, with three near misses correctly refused and two of three unsupported details correctly refused.

The four requests used 12,160 cache-hit input tokens, 780 cache-miss input tokens, and 2,051 completion tokens. Provider-reported usage at the off-peak price gives **¥0.00922720**, with **¥0 unknown exposure**. The four-request preflight reserved **¥0.242368** at peak rates using uncached UTF-8 request bytes plus framing and the entire output allowance. The usage-derived charge has no separate invoice reconciliation. [Official DeepSeek CNY pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing).

## Targeted human and rule-assisted review

The seven-answer sample included both Flash-accepted procedures with incomplete mapped coverage, all three definition answers and the explanation answer whose routes fell from three queries to one, and the first valid Flash rejection for a definition in frozen dev order. Review checked each of 15 vital nuggets against the original answer and Evidence, including whether every necessary facet was present across the cited excerpts and whether the answer introduced a material error. Twelve of 15 vital nuggets were fully stated and grounded. The four definition and explanation answers affected by excessive splitting passed this review on their original contexts.

| Original Flash decision | Review accepted | Review rejected | Total |
| --- | ---: | ---: | ---: |
| Accepted | 5 | 1 | 6 |
| Rejected | 0 | 1 | 1 |

One procedure had sufficient alternate multi-excerpt support absent from the support table. The other had alternate support for parts of its answer, but omitted requested material and lacked complete Evidence for a key causal mechanism. The valid rejection control omitted required elements. The sample shows **leniency on one valid acceptance** and no observed false rejection. The sample was selected to investigate specific failure modes and cannot establish a population bias. The replay's two still-invalid judgments are excluded from the agreement table. The frozen support groups, gold, scoring rules and valid historical judgments were retained.

## Offline retrieval replay

All configurations used the same 30 development items, 356 published excerpts, 1,006 embedding chunks, frozen support groups and MiniLM revision. The replay traversed the signed Java Evidence controller, PostgreSQL cosine ranking and the Light Tutor context builder. Full coverage requires at least one complete frozen support group per vital nugget in the final deduplicated `current_evidence` after authoritative READ. Nugget coverage counts complete groups at the nugget level.

- **Merged product** uses the product entry point at `ef6fcd2b9fc566df92cb7f98fc98de561e911737`. It uses single-query hybrid Top 8 and hybrid Top 16 per planned query on its broader multipart route. Its 30 per-item records matched the previous offline product replay.
- **Submitted product** holds both retrieval strategies constant and changes only how the question is routed. The whole question is always queried. A recognized comparison or distinct course locations can add up to two focused queries. Explicit location cues include timestamps and references to separate parts or examples.
- **Submitted route with neighbors** runs the same query plan as the submitted product. Every query, including the single-query path, uses hybrid Top 8 plus neighbors. The same fusion, authority checks and 16-excerpt cap apply. The two submitted-route rows isolate the retrieval strategy difference.

Query counts, distinct excerpts and UTF-8 context bytes are **means / nearest-rank P95**. UTF-8 bytes count the serialized Evidence array only, as a conservative token proxy. Instructions, dialogue, the question and completion are outside that byte count.

| Configuration | Category | Full vital coverage | Nugget coverage | Queries | Distinct excerpts | Evidence bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Merged product | Answerable | 18/24 | 37/49 | 2.00 / 3 | 12.00 / 16 | 11,150 / 16,439 |
| | Definition | 5/6 | 10/12 | 2.33 / 3 | 13.33 / 16 | 12,499 / 16,439 |
| | Explanation | 4/6 | 5/9 | 1.33 / 3 | 9.33 / 16 | 8,737 / 14,172 |
| | Procedure | 4/6 | 10/15 | 1.33 / 3 | 9.33 / 16 | 8,382 / 14,625 |
| | Comparison | 2/3 | 5/6 | 3.00 / 3 | 16.00 / 16 | 15,001 / 17,067 |
| | Cross-segment | 3/3 | 7/7 | 3.00 / 3 | 16.00 / 16 | 14,963 / 16,354 |
| Submitted product | Answerable | 12/24 | 28/49 | 1.33 / 3 | 9.33 / 16 | 8,696 / 14,637 |
| | Definition | 3/6 | 7/12 | 1.33 / 3 | 9.33 / 16 | 8,610 / 13,207 |
| | Explanation | 3/6 | 4/9 | 1.00 / 1 | 8.00 / 8 | 7,645 / 8,286 |
| | Procedure | 4/6 | 10/15 | 1.00 / 1 | 8.00 / 8 | 7,139 / 7,253 |
| | Comparison | 2/3 | 5/6 | 3.00 / 3 | 16.00 / 16 | 15,130 / 17,067 |
| | Cross-segment | 0/3 | 2/7 | 1.00 / 1 | 8.00 / 8 | 7,650 / 8,069 |
| Submitted route with neighbors | Answerable | 19/24 | 43/49 | 1.33 / 3 | 15.50 / 16 | 14,403 / 16,369 |
| | Definition | 6/6 | 12/12 | 1.33 / 3 | 15.33 / 16 | 14,414 / 15,793 |
| | Explanation | 5/6 | 8/9 | 1.00 / 1 | 15.17 / 16 | 14,457 / 16,369 |
| | Procedure | 4/6 | 12/15 | 1.00 / 1 | 15.50 / 16 | 13,733 / 14,886 |
| | Comparison | 2/3 | 5/6 | 3.00 / 3 | 16.00 / 16 | 14,966 / 16,674 |
| | Cross-segment | 2/3 | 6/7 | 1.00 / 1 | 16.00 / 16 | 15,047 / 15,660 |

The three cross-segment questions depended on implicit course structure. Their text did not identify two distinct course locations, so each used one query on the narrowed route. The four retained multi-query plans were the three comparisons and one explicitly comparative item classified as a definition by the development rubric. These offline coverage results carry no new answer or refusal judgments.

| Configuration | Should-abstain items | Queries | Distinct excerpts | Evidence bytes |
| --- | --- | ---: | ---: | ---: |
| Merged product | All six | 1.00 / 1 | 8.00 / 8 | 7,404 / 8,362 |
| | Three near misses | 1.00 / 1 | 8.00 / 8 | 7,196 / 8,164 |
| | Three unsupported details | 1.00 / 1 | 8.00 / 8 | 7,611 / 8,362 |
| Submitted product | All six | 1.00 / 1 | 8.00 / 8 | 7,404 / 8,362 |
| | Three near misses | 1.00 / 1 | 8.00 / 8 | 7,196 / 8,164 |
| | Three unsupported details | 1.00 / 1 | 8.00 / 8 | 7,611 / 8,362 |
| Submitted route with neighbors | All six | 1.00 / 1 | 15.67 / 16 | 14,610 / 16,342 |
| | Three near misses | 1.00 / 1 | 16.00 / 16 | 14,552 / 15,809 |
| | Three unsupported details | 1.00 / 1 | 15.33 / 16 | 14,668 / 16,342 |

To reproduce, follow the [original isolated fixture setup](README.md#reproduction) with the same private inputs. Use the `product` results from `score candidate` at each revision. For the matched neighbor row, run the scorer with `("HYBRID_8_NEIGHBORS", "HYBRID_8_NEIGHBORS")` as the simple and complex strategy pair in `ROUTED` at the submitted revision. Calculate the query summary from the per-item `queries` field and all byte and excerpt summaries from the same per-item files.
