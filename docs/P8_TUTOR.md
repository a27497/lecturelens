# P8 course Tutor — experimental, offline only

The learner opens **Tutor 对话** in a course workspace, submits a question, follows up in the same conversation, and opens inline citation chips to inspect the course source. Socratic mode asks a guiding question; the next completed reply includes evidence-grounded feedback. The product uses deterministic providers only. Separate v8 eval trials passed bounded known-course gates; v9 has offline verification only; P8 does not inherit AU or P7 quality results.

## Ownership and execution

`lecturelens_real_eval.tutor` owns learning decisions, context, execution and artifacts in Python/PostgreSQL. Java authenticates the browser, checks course access/readiness, obtains the authoritative revision, signs forwarding requests and checks access/revision again before returning. Java has no Tutor tables, migration or learning logic. Python never writes MySQL.

A model first selects `search_tutor_evidence(query)`. Authorized Java SEARCH observations, followed by authoritative READ, affect the next decision: search again or `finish_tutor_turn`. Citable IDs are the first-appearance ordered, de-duplicated union of all search observations in the current turn (at most two searches × eight IDs = 16). The durable `selected` checkpoint starts empty each turn; prior-turn citations and history never authorize IDs. The model sees authoritative READ evidence in that same union order; Python reads in batches of at most eight IDs to preserve the Java authority cap. The union is never silently truncated, and larger requests remain subject to the existing reservation and request caps. Publication re-READs all citations in the learner/course/revision scope and performs a final authority CHECK. The model cites claims inline as `[id]` in text/evaluation and has no separate `evidence_ids` tool field. The controller extracts candidates with the shared source-ID grammar, de-duplicates in first-appearance order (text then evaluation), and assembles the published citation list. Legacy provider declarations are ignored regardless of value. Square brackets remain reserved for citations; ordinary math/index brackets retain their existing parser behavior. Every extracted ID, including those beyond the fourth, must be observed and authoritatively re-READ before any repair; unobserved IDs fail with `TUTOR_CITATION_MISMATCH`.

More than four distinct inline IDs, evaluation over 500 characters and text over 1,600 characters share one `TUTOR_FINISH_REPAIR_REQUIRED` observation. It lists the complete extracted list, distinct count, excess IDs beyond the first four and all actual sizes/exact limits. The committed journal counts this chance across restart, including legacy size/mismatch observations. A second violation fails with `TUTOR_FINISH_FORMAT_INVALID`. Publication revalidates controller-assembled metadata and unchanged content against the original strict `Finish` schema (4/500/1600). No truncation, citation dropping or content/outcome rewriting occurs. Supported finishes with zero inline IDs remain fatal; the exact abstention contract and other schema/type failures retain their existing checks.

A supported Socratic finish must use `socratic_prompt` and contain `?` or `？`; a supported non-Socratic finish must use `answered`. One separate `TUTOR_SOCRATIC_REPAIR_REQUIRED` observation states the required rule. Its durable one-shot counter is independent of format repair; a second violation fails with `TUTOR_SOCRATIC_CONTRACT`. Exact abstention is exempt from these outcome/question rules. Each rejected finish consumes a tool slot and checkpoints `ready`, without publishing an answer.

`insufficient_evidence` requires zero citations, empty evaluation and the exact protocol abstention: “I don't know from this course. Try asking about a topic covered in this lecture.” A contradictory or substantive candidate is rejected, never rewritten into an accepted abstention. The UI shows a clear Chinese insufficient-evidence state. Citation existence is a mechanical guarantee; semantic support needs separate evaluation.

## Persistent state and failure boundaries

Idempotent startup DDL follows the Agent service's existing initialization mechanism under its migration advisory lock:

- `tutor_session`: owner/course/revision, active/stale status, persistent call/token limits, extractive summary and summary cursor.
- `tutor_turn`: client turn ID, ordinal, learner text, mode, status/outcome, published answer/evaluation, canonical citations, usage, call/tool/token counters, deadline, response/observation checkpoint and safe error code. Unique `(session_id,client_turn_id)` and `(session_id,ordinal)` plus a partial unique active-turn index serialize turns.

CREATE uses a deterministic scoped request key. TURN replay returns the original turn, including failed/cancelled turns; changed text or mode with the same key conflicts. One active turn per session. Submission returns queued state; the panel polls authenticated GET, so refresh recovers saved work. Unknown HTTP outcomes retain the original client key for retry.

Each turn permits at most two searches, four ordinary model/tool slots and at most one additional repair-only slot (five total), 64,000 conservatively reserved tokens and a persisted 20-second deadline. Format and Socratic repair each atomically commit the exact next finish-only request and its prepaid model-call/token reservation with the observation and charged rejected tool. Dispatch consumes that reservation once; it cannot make another search or reset the deadline. A crash before dispatch may resume the prepaid request; a crash after dispatch reservation still fails closed as unknown. Session/token caps are unchanged. If capacity cannot be reserved, `TUTOR_REPAIR_BUDGET_UNAVAILABLE` terminates before issuing an observation. An issued repair therefore cannot exhaust its next runtime model/tool budget. Authority, cancellation, deadline and the independent eval ledger can still stop it.

After two searches only `finish_tutor_turn` is offered; an ignored search limit yields an error observation without another authority SEARCH. Missing non-empty evaluation after a Socratic prompt retains `TUTOR_EVALUATION_REQUIRED` and its existing ordinary-budget behavior; it gets no separate one-shot allowance or prepaid slot. Exact insufficient-evidence abstention still requires empty evaluation. Sessions permit 40 submitted turns, 60 model calls and 640,000 reserved tokens. Whole UTF-8 message/schema bytes plus 1,200 output tokens are reserved before provider entry. Failed/unknown reservations are not refunded. Context contains the last six completed turns plus a rolling extractive summary of older turns, capped at 2,000 characters. This is conversation context, not long-term learner memory.

A PostgreSQL session advisory lock admits one executor. The journal commits `reserved` before model I/O, then `received` with the response before executing its tool. Observation/publication and their checkpoint commit atomically. Restart reuses saved responses/observations; an unresolved model reservation fails closed without resending. Cancellation commits terminal state under the same session/turn lock order; a late response cannot publish. Shutdown prevents late publication. A new client ID does not reset session budgets.

A revision change marks sessions stale and fails queued/running turns; stale history cannot be reopened as current evidence. Evidence tombstones block reads/publication immediately and the Tutor worker periodically purges sessions with cascading turns. Before tombstone delivery, Java authority checks still deny deleted courses. Source changes between Python publication and Java response are hidden by the gateway's final revision check.

## Integration and rollback

The frozen `lecturelens_agent` package, package metadata, AU/P7 manifests and offline CostPolicy remain unchanged. Tutor uses a new subpackage of the already packaged `lecturelens_real_eval` namespace to preserve P7's metadata hash; the product modules do not import the paid eval channel. The new opt-in ASGI entry point `lecturelens_real_eval.tutor.app:create_app` wraps the original application, preserving its retrieval, Study Agent and model routes. Tutor is disabled unless `TUTOR_ENABLED=true`; the product factory also requires `AGENT_LLM_MODE=mock`. It never installs a real provider. Java's existing `STUDY_AGENT_ENABLED` controls gateway access.

Start the Python service from `agent-service/`, with the normal service configuration plus the two explicit mock settings:

```bash
TUTOR_ENABLED=true AGENT_LLM_MODE=mock uv run --offline \
  --env-file ../.env.agent.local uvicorn lecturelens_real_eval.tutor.app:create_app --factory \
  --host 127.0.0.1 --port 8090
```

The env file must not override those mock settings. Java retains the existing Agent service URL/secret and course authority configuration. No deployment was performed. Rollback disables Tutor or restores the original ASGI entry point, stops its worker and retains the additive PG tables. It does not rename states or hand Tutor work to legacy Study workers.

The [API reference](API.md#p8-tutor-experimental) lists the authenticated endpoints. Offline checks, dialogue scripts, frozen thresholds, ledger policy and the unexecuted live command are in [eval/p8-tutor](../eval/p8-tutor/README.md). Test results are recorded in its [report](../eval/p8-tutor/REPORT.md).

The eval reviewer sees publication status in conversation history. An invented antecedent after a failed/unpublished prior turn must score `context_retained=false`; the runner also downgrades answered context follow-ups unless they are explicit clarification questions. This rule never upgrades reviewer judgments. Abstention/clarification is exempt from that downgrade. Report-only over-abstention diagnostics split cascade turns (immediately preceded by a failed/unpublished turn) from the remainder.

The v6 script correction expects abstention for union-bound turns 1–3 of `probability-l1-3`, because that lecture has no union-bound evidence; turn 4 already expects abstention for its absent Dirichlet extension and is unchanged. See the [v6 report](../eval/p8-tutor/REPORT.md#offline-controller-assembled-citations-v6) for the freeze and offline checks.

## Limits and planned work

Implemented: bounded course conversation, context window/summary, source checks, explicit abstention, Socratic protocol and next-turn feedback, persistence/replay/cancellation, Java gateway and Vue panel. Experimental: source relevance, semantic answer support, context retention and pedagogical value. The deterministic mock extracts source text and provides a comparison hint; it does not grade a learner or demonstrate model intelligence.

Planned: independently measured real-model tutoring, broader unseen-course evaluation, stronger semantic verification and learner feedback. Long-term memory, automatic grading, adaptive mastery and review scheduling are outside P8. The snapshot eval uses public PDF evidence and synthetic page slots inherited from P7, not real media timestamps. It is separate from product media citation navigation.
