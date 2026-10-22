# Structured Tutor learning scope

PR2 candidate, not deployed. Scope enforcement changes execution mechanics; deterministic providers do not establish teaching quality.

## Learner behavior

The course workspace offers a shared selection for course QA and Study Agent: the whole course, or up to 16 canonical Evidence passages with nonempty time intervals. Passages retain their actual modality, identity, revision and time bounds. Pagination and filtering apply to loaded Evidence; full translations are not converted into aligned passages.

A segment selection has an explicit policy:

- `strict`: search, reads, neighboring context and model context remain inside the selected IDs. No hits yield an insufficiency response or a stopped execution; retrieval never silently widens.
- `course`: course QA searches selected passages first and retries the authorized whole-course pool only when there are no hits. The Agent can explicitly set `expand_to_course: true` on search; reads and neighboring context may use the authorized course. This is permission to expand, not a requirement to expand every task.

Changing the next selection does not rewrite an existing Run. Its frozen scope is shown separately, including after reload. A page reload resets the next selection to the current whole course; it restores saved learning records through the existing Session API. Unsaved inputs retain the existing PR1 continuity rules. A revision change invalidates the next selection until the learner confirms it again. Late course pages and QA responses cannot replace a newer selection/course state.

## Boundary and persistence

`learning_scope` is a versioned object on QA requests and Study `START` commands:

```json
{"version":1,"kind":"segments","policy":"strict","revision":1,"evidence_ids":["canonical-evidence-id"]}
```

Whole course uses `kind: "course"`, `policy: "strict"` and an empty ID list. IDs do not grant access. Java first resolves the authenticated owner, course and current revision, then checks selection membership against that owner's canonical Evidence snapshot. Existing deletion and generation fences run before and after retrieval. Filtering happens before lexical/dense ranking and before adjacent context selection. Signed Agent/MCP requests carry the frozen selection; a missing or different authority echo fails closed before model execution.

Python stores the normalized selection in the existing `study_run.learning_scope` JSONB column. Request-key replay compares it. Feedback inherits its source practice Run's scope. Recent Session context is restricted to exactly the same frozen scope; broader historical artifacts cannot enter a new strict task. The scope is not a model-writable tool parameter. Tool retries, checkpoint recovery, approval and cancellation use the existing Run, journal, budgets and worker-token fences.

The additive PostgreSQL initialization installs a scope-immutability/feedback-inheritance trigger and a unique active-Run index spanning legacy and scoped states. Active scoped Runs use `queued_scoped_v1`, `running_scoped_v1` and `awaiting_approval_scoped_v1` internally; API statuses remain unchanged. Old workers cannot poll these states. There is no MySQL schema change or second permission system.

## Compatibility and rollout

Absent scope on legacy requests/Runs retains the existing whole-course contract and current owner/revision/deletion checks. Old artifacts, answers, feedback and canonical citation navigation require no conversion. New Runs may share a Session while selecting different scopes; each remains independent.

The Evidence page advertises `learningScopeVersion: 1`. New UI actions remain disabled against an older Java server. New Python rejects an authority response that omits its scoped echo. Old Python rejects the new command field. Deploy all compatible components only after independent review and separate deployment authorization. Mixed versions should fail closed; they are not a supported permanent topology.

Before deployment, verify the production database DDL permissions, backup/recovery plan, complete long-course performance, authenticated real business APIs/media authorization, supported browsers, and real-provider task quality under an explicitly authorized budget. Existing PR1 deployment conditions still apply. No real-model quality or production acceptance is inferred from mock execution tests.

To roll back, stop scoped execution through the normal authorized release process and restore the previous application artifacts together. Keep the additive column, index and trigger: old workers will leave pending scoped Runs untouched, while legacy records remain readable. Do not clear scopes, rename queued scoped states to legacy states, drop the fence, or delete checkpoints to make old workers resume them. Resuming those Runs requires a scope-aware version. Removing additive DDL is a separate reviewed migration after all dependent records are handled.

## Verification entry points

- `agent-service/tests/test_learning_scope.py`: contracts, strict tool/echo boundaries, actual PostgreSQL freezing, idempotency, context isolation, cancellation, approval/checkpoint recovery, feedback inheritance and legacy-worker isolation.
- `StudyAuthorityTest`, `CourseQaServiceTest`: candidate-pool constraints, explicit expansion and refusal without a model call.
- `LearningScopeMySqlIT`: explicit integration target using all real Flyway migrations, canonical ownership, course membership, revision and deletion boundaries. It fails when the dedicated database is absent; it is not a silently skipped default unit test. Supply `SYSTEM_MODEL_TEST_JDBC_URL` pointing to a disposable loopback `lecturelens_pr2_test` database with `utf8mb4_unicode_ci`, plus the test user/password variables, and run `mvn -Dtest=LearningScopeMySqlIT test`.
- Frontend component tests cover selection, revision changes, delayed course pages, frozen scope and late QA responses. `coursePosition.mjs` retains real Chrome/media navigation regression tests with fixture business responses.

Run long local checks under the repository's process supervisor where available. Test databases, build output and browser services must be isolated from running deployments. Keep generated media, database credentials and acceptance records outside Git.
