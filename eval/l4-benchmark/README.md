# L4 AI Benchmark: RAG vs Light Tutor vs Study Agent

The benchmark asks how LectureLens Course QA (RAG), Light Tutor and the Study Agent compare on the same course questions. It measures correctness, citation quality, appropriate abstention, cost and latency.

**Scope.** The benchmark is AI-authored and synthetic. Kiro wrote the questions and the nugget gold from official captions, and Codex audited the full content. Its purpose is to compare product paths on identical items; it does not rank models.
- All three paths use `deepseek-flash`.
- The judge is `deepseek-v4-pro`, from the same vendor.
- The holdout has 6 lectures from 3 MIT OpenCourseWare courses. The confidence intervals do not cover course selection.

Question text, gold, captions and model outputs stay private. This directory holds only hashes, counts and aggregate results:
- [freeze.json](freeze.json): the frozen PLAN, question sets and gold audits, with the freeze history.
- [results.json](results.json): every pre-registered metric with its interval, paired differences, latency, cost, failure categories and judge agreement.

## Capability labels

| Capability | Label |
| --- | --- |
| Product calls (RAG, Tutor runtime, Study Run) | Real: `deepseek-flash`, official captions embedded as subtitles |
| Judge | Real: `deepseek-v4-pro`, prompt `l4-judge-v2-r2` |
| ASR, vision, OCR | NOT_RUN |
| Java Tutor HTTP gateway and trial receipt | NOT_RUN (Tutor was run through the product runtime directly) |
| Harness, scoring and freeze | Offline tests |

## Holdout results

96 items (72 answerable, 24 should-abstain) × 3 repetitions. The intervals are 95% bootstraps stratified by lecture.

| Metric | RAG | Light Tutor | Study Agent |
| --- | --- | --- | --- |
| **Strict correct** (all vital nuggets supported, no material error) | **0.417** [0.31, 0.52] | **0.718** [0.62, 0.81] | **0.426** [0.34, 0.52] |
| Lenient (vital nuggets, partial = 0.5) | 0.636 [0.55, 0.72] | 0.836 [0.76, 0.90] | 0.529 [0.45, 0.62] |
| Material error (answered answerable) | 0.186 | 0.080 | 0.024 |
| Citation recall (ALCE) | 0.881 | 0.827 | 0.976 |
| Citation precision (ALCE pairs / distinct) | 0.537 / 0.914 | 0.883 / 0.924 | 0.255 / 0.605 |
| Abstention accuracy | 0.931 | 0.941 | 0.677 |
| Product failure rate | 0 / 288 | 1 / 288 | 83 / 288 |
| P50 / P95 latency | 1.10 / 1.62 s | 4.45 / 7.76 s | 14.5 / 23.6 s |
| Cost per question (ledger, official prices) | USD 0.00037 | USD 0.00075 | USD 0.0074 |

Product failures count as incorrect, and as wrong abstention decisions.

**Paired differences.**
- On strict correct, Tutor leads RAG by +0.30 [+0.19, +0.42] and Study by +0.29 [+0.17, +0.42], with Bonferroni-adjusted intervals.
- Exact McNemar on repetition 1 gives p = 1.5×10⁻⁶ (Tutor vs RAG) and p = 3.2×10⁻⁴ (Tutor vs Study).
- The RAG vs Study comparison is inconclusive: −0.01, and the adjusted interval [−0.14, +0.12] includes zero.

**Study failures.** Of the 83 failures, 63 are `MODEL_REVIEW_CONTRACT` and 11 are `RUN_BUDGET_EXCEEDED`. On the answerable attempts that Study answered (no failure and no abstention), 92 of 126 are strictly correct (exploratory).

## Judge reliability

Three blind Codex reviewers re-graded a seeded 20.6% sample (161 responses, stratified by course and path).

| Measure | Value |
| --- | --- |
| Verdict agreement | 88.2%, Cohen's κ 0.75 |
| Nugget-label agreement | 87.5%, κ 0.78 |
| Citation full-support agreement | 77.0%, κ 0.44 |

**Direction.** The judge was more lenient than the reviewers. It marked CORRECT 18 responses that the reviewers marked INCORRECT, and the reverse happened once. Most of those cases are a vital nugget the judge counted as supported and the reviewer as partial.
- Agreement is lowest on Study: κ 0.54, against 0.79 for RAG and 0.83 for Tutor.
- This direction is observed on the reviewed sample only, which excludes product failures. It is not a bound on the full holdout scores.
- Citation metrics are less reliable than correctness.

**Ranking check (exploratory).** The sample covers every response with status `ok`, including declared abstentions, and excludes product failures. The counts below are CORRECT verdicts over the sampled answerable items of each path.
- On this sample the judge rates Study at 18/24 and Tutor at 29/41. The reviewers give Tutor 24/41 and Study 11/24.
- Tutor's lead in the primary metric comes from RAG's lower correctness and from Study's failure rate.
- The lead survives a reviewer-calibrated adjustment: each path's strict score is scaled by its reviewer/judge CORRECT ratio on the sample. This gives RAG about 0.31, Tutor 0.59 and Study 0.26.

## Method and history

The pre-registered PLAN went through revisions:
- nugget gold after two gold-audit rounds;
- the judge, frozen after two dev rounds;
- holdout execution changes;
- account-level events.

Each revision records its reason and was frozen before any holdout result was read. The 2026-11-18 account event (09:21:52–09:23:12 UTC) hit the account concurrency limit and then ran out of balance. 26 product units and 1 judge decision were repeated once. Product failures outside that window are reported as product outcomes and were never rerun.

The harness is in `agent-service/src/lecturelens_real_eval/l4/`, with offline tests in `agent-service/tests/test_l4_benchmark.py`.
