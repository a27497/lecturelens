# Retrieval v2 results

Frozen AI-assisted qrels; not human gold or Study Agent answer quality.
Family CI conditions on sampled courses; course/family CI also resamples courses. Holdout has only two courses.

## development

|Method|Answerable N|Recall@1/3/5/8|MRR@3|nDCG@3|Coverage@3 [family CI95]; [course/family CI95]|P50/P95 ms [CI95]|
|---|---:|---|---:|---:|---|---|
|dense|64|19.01/42.97/52.08/56.90|0.4036|0.3697|48.44 [39.04, 57.81]; [23.44, 73.44]|38.95 [37.73, 39.69] / 45.29 [43.91, 46.16]|
|bm25_dense|64|20.83/37.24/53.65/57.81|0.4010|0.3272|46.09 [36.72, 55.47]; [25.78, 66.41]|50.08 [49.33, 52.14] / 59.98 [57.89, 61.59]|
|hybrid_rrf|64|18.75/38.02/48.18/59.38|0.4062|0.3283|48.44 [39.06, 57.03]; [27.34, 68.75]|49.70 [49.09, 51.68] / 60.07 [58.73, 61.94]|
|hybrid_rrf_ce|64|26.30/50.52/58.59/59.38|0.4844|0.4520|53.91 [44.53, 63.28]; [22.66, 84.38]|826.99 [795.38, 887.18] / 1400.99 [1215.18, 1425.55]|

Prespecified paired Coverage@3 contrasts to Dense (percentage points; simultaneous Bonferroni intervals):

- bm25_dense_minus_dense: -2.34; family [-10.16, 4.69]; course/family [-13.28, 8.86]
- hybrid_rrf_minus_dense: 0.00; family [-8.59, 8.08]; course/family [-12.50, 14.06]
- hybrid_rrf_ce_minus_dense: 5.47; family [-3.12, 13.28]; course/family [-7.81, 17.97]

Failure bucket counts/shares and all per-metric CIs at K=1/3/5/8 are in summary.json; every failed query is retained in failures.json.

## holdout

|Method|Answerable N|Recall@1/3/5/8|MRR@3|nDCG@3|Coverage@3 [family CI95]; [course/family CI95]|P50/P95 ms [CI95]|
|---|---:|---|---:|---:|---|---|
|dense|32|30.73/50.52/64.58/65.62|0.5208|0.4653|53.12 [34.38, 70.31]; [31.25, 70.31]|39.31 [38.70, 40.56] / 46.46 [42.18, 47.73]|
|bm25_dense|32|25.00/39.58/61.46/68.23|0.4531|0.3696|48.44 [25.00, 68.75]; [25.00, 68.75]|52.06 [50.78, 53.86] / 59.56 [56.99, 65.88]|
|hybrid_rrf|32|29.17/42.19/54.69/68.23|0.5000|0.4040|51.56 [32.81, 68.75]; [29.65, 68.75]|52.98 [52.59, 53.33] / 61.29 [57.76, 65.52]|
|hybrid_rrf_ce|32|40.62/54.17/65.62/68.23|0.5990|0.5373|57.81 [48.44, 68.75]; [34.38, 73.44]|662.01 [620.40, 728.96] / 1120.31 [945.67, 1663.85]|

Prespecified paired Coverage@3 contrasts to Dense (percentage points; simultaneous Bonferroni intervals):

- bm25_dense_minus_dense: -4.69; family [-10.94, 0.00]; course/family [-17.19, 0.00]
- hybrid_rrf_minus_dense: -1.56; family [-4.69, 0.00]; course/family [-6.78, 0.00]
- hybrid_rrf_ce_minus_dense: 4.69; family [-9.38, 23.44]; course/family [-15.62, 29.19]

Failure bucket counts/shares and all per-metric CIs at K=1/3/5/8 are in summary.json; every failed query is retained in failures.json.

## all

|Method|Answerable N|Recall@1/3/5/8|MRR@3|nDCG@3|Coverage@3 [family CI95]; [course/family CI95]|P50/P95 ms [CI95]|
|---|---:|---|---:|---:|---|---|
|dense|96|22.92/45.49/56.25/59.81|0.4427|0.4015|50.00 [41.15, 58.33]; [32.29, 68.75]|38.98 [38.49, 39.67] / 45.60 [44.70, 46.79]|
|bm25_dense|96|22.22/38.02/56.25/61.28|0.4184|0.3413|46.88 [36.98, 56.25]; [31.25, 62.50]|51.03 [50.12, 52.14] / 59.98 [57.89, 61.75]|
|hybrid_rrf|96|22.22/39.41/50.35/62.33|0.4375|0.3535|49.48 [40.62, 57.81]; [34.38, 64.06]|51.67 [50.40, 52.39] / 60.12 [59.32, 62.07]|
|hybrid_rrf_ce|96|31.08/51.74/60.94/62.33|0.5226|0.4804|55.21 [47.92, 62.50]; [33.85, 76.56]|759.31 [735.27, 809.72] / 1399.29 [1207.08, 1425.55]|

Prespecified paired Coverage@3 contrasts to Dense (percentage points; simultaneous Bonferroni intervals):

- bm25_dense_minus_dense: -3.12; family [-8.33, 2.08]; course/family [-11.46, 4.69]
- hybrid_rrf_minus_dense: -0.52; family [-6.25, 5.21]; course/family [-8.85, 8.85]
- hybrid_rrf_ce_minus_dense: 5.21; family [-2.60, 13.02]; course/family [-5.21, 16.15]

Failure bucket counts/shares and all per-metric CIs at K=1/3/5/8 are in summary.json; every failed query is retained in failures.json.

## zh

|Method|Answerable N|Recall@1/3/5/8|MRR@3|nDCG@3|Coverage@3 [family CI95]; [course/family CI95]|P50/P95 ms [CI95]|
|---|---:|---|---:|---:|---|---|
|dense|48|16.67/38.89/50.35/56.25|0.3403|0.3215|40.62 [32.29, 50.00]; [18.75, 61.46]|39.14 [38.50, 39.81] / 46.07 [43.66, 47.86]|
|bm25_dense|48|10.42/30.56/51.04/56.94|0.2535|0.2351|33.33 [22.92, 44.79]; [17.71, 48.96]|52.32 [50.62, 53.93] / 61.53 [57.81, 65.90]|
|hybrid_rrf|48|13.54/33.68/40.62/55.90|0.3056|0.2735|37.50 [28.12, 47.92]; [23.96, 51.04]|51.81 [50.42, 52.65] / 60.30 [58.52, 65.72]|
|hybrid_rrf_ce|48|34.38/49.65/55.90/55.90|0.4965|0.4638|51.04 [40.62, 61.46]; [29.17, 72.92]|662.01 [644.79, 707.76] / 1097.28 [929.65, 1212.19]|

Prespecified paired Coverage@3 contrasts to Dense (percentage points; simultaneous Bonferroni intervals):

- bm25_dense_minus_dense: -7.29; family [-13.54, -1.04]; course/family [-23.96, 4.17]
- hybrid_rrf_minus_dense: -3.12; family [-10.42, 4.17]; course/family [-18.75, 11.46]
- hybrid_rrf_ce_minus_dense: 10.42; family [1.04, 20.83]; course/family [-0.36, 23.96]

Failure bucket counts/shares and all per-metric CIs at K=1/3/5/8 are in summary.json; every failed query is retained in failures.json.

## en

|Method|Answerable N|Recall@1/3/5/8|MRR@3|nDCG@3|Coverage@3 [family CI95]; [course/family CI95]|P50/P95 ms [CI95]|
|---|---:|---|---:|---:|---|---|
|dense|48|29.17/52.08/62.15/63.37|0.5451|0.4815|59.38 [45.83, 71.88]; [35.42, 82.29]|38.95 [38.39, 39.66] / 45.29 [43.03, 47.75]|
|bm25_dense|48|34.03/45.49/61.46/65.62|0.5833|0.4475|60.42 [47.92, 72.92]; [35.42, 82.29]|50.46 [49.49, 51.57] / 59.88 [56.59, 60.04]|
|hybrid_rrf|48|30.90/45.14/60.07/68.75|0.5694|0.4336|61.46 [48.96, 73.96]; [37.50, 83.33]|51.29 [49.67, 52.54] / 60.11 [57.75, 61.17]|
|hybrid_rrf_ce|48|27.78/53.82/65.97/68.75|0.5486|0.4970|59.38 [48.96, 69.79]; [31.25, 84.38]|888.90 [811.50, 944.53] / 1425.55 [1364.43, 1576.80]|

Prespecified paired Coverage@3 contrasts to Dense (percentage points; simultaneous Bonferroni intervals):

- bm25_dense_minus_dense: 1.04; family [-6.25, 9.38]; course/family [-8.33, 10.42]
- hybrid_rrf_minus_dense: 2.08; family [-6.25, 10.42]; course/family [-8.33, 11.46]
- hybrid_rrf_ce_minus_dense: 0.00; family [-11.46, 10.42]; course/family [-16.67, 15.62]

Failure bucket counts/shares and all per-metric CIs at K=1/3/5/8 are in summary.json; every failed query is retained in failures.json.

## cross-lecture

|Method|Answerable N|Recall@1/3/5/8|MRR@3|nDCG@3|Coverage@3 [family CI95]; [course/family CI95]|P50/P95 ms [CI95]|
|---|---:|---|---:|---:|---|---|
|dense|24|14.58/27.78/35.42/39.24|0.4583|0.2896|33.33 [33.33, 33.33]; [20.83, 45.83]|40.51 [40.51, 40.51] / 46.39 [46.39, 46.39]|
|bm25_dense|24|11.81/25.00/35.42/40.97|0.4444|0.2573|33.33 [33.33, 33.33]; [22.92, 41.67]|51.81 [51.81, 51.81] / 60.01 [60.01, 60.01]|
|hybrid_rrf|24|13.89/26.39/32.64/47.22|0.4931|0.2832|35.42 [35.42, 35.42]; [25.00, 45.83]|53.58 [53.58, 53.58] / 59.68 [59.68, 59.68]|
|hybrid_rrf_ce|24|18.06/34.03/45.83/47.22|0.5556|0.3653|41.67 [41.67, 41.67]; [27.08, 56.25]|776.43 [776.43, 776.43] / 1358.14 [1358.14, 1358.14]|

Prespecified paired Coverage@3 contrasts to Dense (percentage points; simultaneous Bonferroni intervals):

- bm25_dense_minus_dense: 0.00; family [0.00, 0.00]; course/family [-10.42, 12.50]
- hybrid_rrf_minus_dense: 2.08; family [2.08, 2.08]; course/family [-10.42, 14.58]
- hybrid_rrf_ce_minus_dense: 8.33; family [8.33, 8.33]; course/family [-4.17, 20.83]

Failure bucket counts/shares and all per-metric CIs at K=1/3/5/8 are in summary.json; every failed query is retained in failures.json.
