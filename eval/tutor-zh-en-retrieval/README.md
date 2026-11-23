# Chinese queries on English Light Tutor transcripts

This development replay measures support in the final Evidence sent to Light Tutor. It uses the three L4 development lectures and no holdout data. The base is the post-#92 squash `b02ca48981a4d60589ac92463c53d5d04fb9df96`.

**No candidate selected.** Both translation arms recovered additional support overall and failed the cross-segment guardrail in the preregistered run. In the authorized isolation check, fallback restored baseline coverage on the affected question. The draft preserves the original default and the two experimental arms for review.

The 42 approved inputs include 24 Chinese answerable prompts, 12 English answerable controls, and six required-refusal controls. The Chinese slice has six definitions, six explanations, six procedures, three comparisons, two cross-segment questions, and one within-segment multipart question. Twelve Chinese prompts are independently reviewed mirrors of existing development English prompts. The independent review checked all 42 prompts and 55 distinct sufficient alternatives across 50 vital labels. The English controls add 25 case-level vital labels. The three source snapshots use 178 English original excerpts. Existing translated captions were excluded from this isolated projection so the replay measures Chinese questions against English transcripts.

Each vital nugget is covered when every Evidence ID in at least one of its approved alternative groups appears in the exact deduplicated `current_evidence` after Java READ. Full coverage requires every vital nugget. The refusal inputs have no accepted vital support groups. Nonempty retrieval for one of those inputs measures context exposure, with no Tutor answer or refusal judgment. The replay did not run either the answer provider or a judge.

## Development results

Each coverage cell shows fully covered questions and covered vital nuggets. Both runs used 42 inputs per arm, with three fixed arms and the same original query decomposition, hybrid ranking strategies and final fusion. Each compared the disabled current runtime with the pinned baseline on 42 further prepared states. Baseline parity was exact in both runs. All four signed authority rejection checks passed per run. Translation added no Evidence requests.

| Stratum | Original, both runs | English, first | Bilingual, first | English, isolated | Bilingual, isolated |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chinese answerable | 14/24 · 38/50 | 19/24 · 43/50 | 18/24 · 41/50 | 19/24 · 44/50 | 18/24 · 42/50 |
| Definition | 4/6 · 10/12 | 5/6 · 11/12 | 5/6 · 11/12 | 5/6 · 11/12 | 5/6 · 11/12 |
| Explanation | 3/6 · 5/9 | 5/6 · 7/9 | 5/6 · 8/9 | 5/6 · 7/9 | 5/6 · 8/9 |
| Procedure | 4/6 · 13/16 | 5/6 · 15/16 | 4/6 · 12/16 | 5/6 · 15/16 | 4/6 · 12/16 |
| Comparison | 1/3 · 4/6 | 2/3 · 5/6 | 2/3 · 5/6 | 2/3 · 5/6 | 2/3 · 5/6 |
| Cross-segment | 1/2 · 4/5 | 1/2 · 3/5 | 1/2 · 3/5 | 1/2 · 4/5 | 1/2 · 4/5 |
| Within-segment multipart | 1/1 · 2/2 | 1/1 · 2/2 | 1/1 · 2/2 | 1/1 · 2/2 | 1/1 · 2/2 |
| English answerable | 8/12 · 21/25 | 8/12 · 21/25 | 8/12 · 21/25 | 8/12 · 21/25 | 8/12 · 21/25 |
| All answerable | 22/36 · 59/75 | 27/36 · 64/75 | 26/36 · 62/75 | 27/36 · 65/75 | 26/36 · 63/75 |

| Paired Chinese changes vs original | First full gain/loss | First vital gain/loss | Isolated full gain/loss | Isolated vital gain/loss |
| --- | ---: | ---: | ---: | ---: |
| English | 5/0 | 7/2 | 5/0 | 7/1 |
| Bilingual | 5/1 | 6/3 | 5/1 | 6/2 |

The frozen gate requires at least two net additional fully covered Chinese questions, improved micro vital coverage, preservation of both comparison and cross-segment counts, exact English output parity, and the context and latency guardrails below. In the first run both variants missed the same cross-segment vital nugget on an item that was already incomplete. The isolated run reproduced all original-arm results. It changed one English-rewrite result and two bilingual results. All three differences were fallbacks to original queries. Both variants fell back on that same cross-segment question and restored the original vital count. Bilingual also fell back on one comparison with identical coverage. The isolated run met the numerical guardrail through fallback. The first outcome remains the selection result, and the holdout remains closed.

| Run | Arm | All context bytes mean/P95 | All elapsed ms mean/P95 | Chinese elapsed ms mean/P95 | Chinese added ms P95 |
| --- | --- | ---: | ---: | ---: | ---: |
| First | Original | 14,531 / 16,493 | 181 / 329 | 181 / 329 | 0 |
| First | English | 14,568 / 16,597 | 907 / 1,740 | 1,324 / 1,741 | 1,477 |
| First | Bilingual | 14,526 / 16,493 | 916 / 1,736 | 1,343 / 1,788 | 1,524 |
| Isolated | Original | 14,531 / 16,493 | 166 / 279 | 166 / 279 | 0 |
| Isolated | English | 14,599 / 16,669 | 903 / 1,725 | 1,332 / 1,734 | 1,492 |
| Isolated | Bilingual | 14,547 / 16,688 | 923 / 1,754 | 1,363 / 1,762 | 1,500 |

Context is UTF-8 bytes of the final serialized Evidence array. The largest variant mean and P95 were 100.5% and 101.2% of baseline, within the 110% bounds. Every arm averaged 15.67 excerpts with P95 and maximum 16. The wall time includes the fresh local MT process, Java SEARCH, vector retrieval, READ and context assembly. Both variants stayed within the Chinese P95 limits of 2,000 ms total and 1,750 ms added. Zero fallbacks occurred in the first run. One English and two bilingual fallbacks occurred in the isolated run.

All 15 English inputs, including three refusal controls, had exactly the same ordered final Evidence and queries across arms. Every refusal control retrieved 16 excerpts. On the three Chinese refusal controls, both variants changed the ordered Evidence on all three items. Their context bytes mean/P95 were 14,244/15,712 original, 14,340/15,400 English and 14,045/15,311 bilingual in both runs. Across all six refusal controls, elapsed ms mean/P95 was 116/139, 633/1,246 and 611/1,172 on the first run, and 113/122, 618/1,273 and 639/1,275 in isolation.

Each replay recorded 126 measured prepares, zero Tutor provider or hosted inference calls and USD 0 spent. The first trace recorded 16 non-loopback connection attempts consistent with the pinned ONNX Runtime wheel's telemetry, even though Hugging Face offline mode was enabled. The connect trace did not establish completion or payload contents. The repeat ran with telemetry disabled and only loopback in a separate Linux network namespace, using a private PostgreSQL Unix socket. Synthetic IPv4 and IPv6 route probes were rejected, and no other non-loopback attempts were recorded.

## Replay

The [replay script](../../scripts/eval/tutor_zh_en_retrieval.py) checks the original preregistration and independent approval against the exact files. It expects the authorized private revision-2 directory with its parent preregistration and predecessor review receipt. Lecture material, prompts, labels and per-item selected Evidence all stay in that private directory. A reviewer with local access can reproduce the experiment with a fresh `lecturelens_agent_test` database with pgvector, the pinned original MiniLM cache, and the existing [loopback Java Evidence fixture](../../backend/src/test/java/com/example/courselingo/study/TutorDevEvidenceServer.java).

| Private input | SHA-256 |
| --- | --- |
| Preregistration, 2026-11-23 | `295dab4698130a2ae89c7747397b009a1e3ad2576585a48c09a93e2ac2637d43` |
| Prior review receipt | `0d305bc50ffc195fc08d849b984f018b85d365b34294f0d65f4504d9dd3a03db` |
| Prereplay amendment | `f02dedc41f41e910a31823e2ad883c28462769791023a7b6f33ebacb16405ad8` |
| Revised input manifest | `ca2958b0ece7a6ff6b1a866d81b20ee898434a52d66ebb7acd087d031a14fc8a` |
| Approved review receipt | `3ce4521a7e72ed273b9870ddff73db4cb4dbbc10d0a5b57a083732e2c73e7985` |
| Prompts | `e6baecd8f04878fb70ec32ffb0bfdbe280c01dc9d6f3c2c2f23554a9ae2ed27c` |
| Sufficient Evidence groups | `1cb01f1a926d87a9eeb1deadc671d5ae732ee2b44653251c914ee39878ae8a8c` |
| Original English Evidence | `971683f22c8337ff08de6bf73cba21c3c9f34cc73eea96fb797370342e52345c` |
| Canonical reviewed prompt/support join | `c6c1515cde687dd72804144d374fb42ed3aa425aeeb87ff6552852aecbef2d01` |
| Review projection | `bb60dfa23cbc7bfc75945bb408ac510f4d31fb09da8e175ae2f0663e75ea6710` |
| Development-source exclusion | `e1f4e61cfe111b91d37a28637ccbf7620b57899abf31ff54a9ea20276df19122` |
| Ordered 728-chunk index manifest | `54cb7ba67f83d4fe485e0513bf42a9a888cba03f09568535b8ae19c2c8a4a46e` |
| First replay aggregate | `f7a4cdde9a60f28e02e3847aa0df0acf99c0dde3cb576e2f932605c3c7829e44` |
| Isolated replay aggregate | `39a9a764f047569808ba9cdeeb82f6a07e4d1e77ac743d4762ff15d9ec486346` |
| Redacted replay comparison and network receipt | `ca5191c0907529236bc3061e9d297a422daf9ea23cadc186e08b5c8a0457fa16` |

The private exclusion manifest identifies the entire courses and records media, caption, transcript, and Evidence digests. MIT OpenCourseWare material is used locally for non-commercial development with attribution and applicable CC BY-NC-SA terms. The source lectures are [18.650 Statistics for Applications](https://ocw.mit.edu/courses/18-650-statistics-for-applications-fall-2016/resources/lecture-7-video/), [6.034 Artificial Intelligence](https://ocw.mit.edu/courses/6-034-artificial-intelligence-fall-2010/resources/lecture-10-introduction-to-learning-nearest-neighbors/), and [7.016 Introductory Biology](https://ocw.mit.edu/courses/7-016-introductory-biology-fall-2018/resources/lecture-4-enzymes-and-metabolism/).

From the repository root, install the worktree's locked dependencies using `uv sync --frozen --offline` in `agent-service`. Use a separate trusted Python 3.12 environment for the optional translator with `ctranslate2==4.6.0` and `sentencepiece==0.2.1`. The replay used NumPy 2.5.5, PyYAML 6.0.4 and setuptools 84.2.1 in that environment. Linux with `libseccomp.so.2` is required for the local translation worker.

Use the [Argos Chinese–English 1.9 archive](https://argos-net.com/v1/translate-zh_en-1_9.argosmodel) with SHA-256 `62e7af5a3a48b530e47b7b3e5c78c2de79073ecd815750d2bf3ab35b4a67da2d`. Its packaged attribution names Jörg Tiedemann and Santhosh Thottingal and identifies the original OPUS-MT model as CC BY 4.0. Verify the archive before extracting it outside the checkout. Set `TUTOR_TRANSLATION_MODEL_DIR` to its extracted `translate-zh_en-1_9` directory and `TUTOR_TRANSLATION_PYTHON` to the absolute interpreter path. The worker checks the four used components against [pinned hashes](../../agent-service/src/lecturelens_real_eval/tutor/query_translation_worker.py), uses CPU inference, disables sockets, and is killed and reaped after 1.5 seconds.

Set `DEV_ROOT` to the approved revision-2 directory, `OUT` to a new private output directory, and `AGENT_TEST_DATABASE_URL` to the dedicated local database. Set `TUTOR_DEV_EMBEDDING_CACHE` to the existing MiniLM cache for revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0`. Use two unused loopback ports `VECTOR_PORT` and `JAVA_PORT`. The processes need the same ephemeral `TUTOR_DEV_SIGNING_KEY`. Run the replay in an egress-blocked Linux network namespace with only loopback up and connect to the dedicated PostgreSQL server over its private Unix socket. The harness sets `ORT_DISABLE_TELEMETRY=1` before loading the embedding runtime. Use an empty `HF_HOME` and the distinct model cache above.

```bash
umask 077
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 STUDY_AGENT_ENABLED=false
export TUTOR_DEV_SIGNING_KEY="$(agent-service/.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
replay=scripts/eval/tutor_zh_en_retrieval.py
agent-service/.venv/bin/python "$replay" "$DEV_ROOT" index "$OUT/java-fixture.json"
(cd backend && ./mvnw -o -B test-compile dependency:build-classpath -Dmdep.outputFile=target/tutor-dev-classpath)
```

Run these services in separate supervised shells with the same environment and keep them available until scoring finishes.

```bash
agent-service/.venv/bin/python "$replay" "$DEV_ROOT" serve-vector "$VECTOR_PORT" "$OUT/vector.jsonl"
```

```bash
java -XX:ActiveProcessorCount=4 \
  -cp "backend/target/test-classes:backend/target/classes:$(cat backend/target/tutor-dev-classpath)" \
  com.example.courselingo.study.TutorDevEvidenceServer "$OUT/java-fixture.json" "$JAVA_PORT" "$VECTOR_PORT"
```

```bash
agent-service/.venv/bin/python "$replay" "$DEV_ROOT" score "$JAVA_PORT" "$OUT/vector.jsonl" "$OUT/private.jsonl" \
  > "$OUT/public-aggregates.json"
```

The baseline executes both Tutor retrieval modules from the pinned commit. The current app is launched with each configured arm and the disabled runtime is checked for exact prepared-state parity on all inputs. The production signed Java controller and dense client, Python embedding and pgvector, authoritative Java READ, and Light Tutor context assembly are exercised. The fixture supplies isolated H2 course records and reviewed deterministic Evidence snapshots. The score operation records each resulting vector snapshot ID and checks wrong-owner, wrong-revision, foreign-excerpt and invalid-signature requests. In normal Tutor checkout the existing scope, version, deduplication and 16-excerpt rules remain enforced.

The three arms retain the original planner and its fixed search count. `original` uses the base query, `english` uses a term-preserving English replacement, and `bilingual` uses the original query followed by the same translation in one search. No extra search is added. Only Han-containing queries on a Chinese turn are eligible. Pure English follows the original route, and errors, timeouts, mismatches or overflow restore the full original query plan. The configured mode defaults to `original`; the optional translator venv and model have no effect on the default installation, existing MiniLM indexes or cold start.
