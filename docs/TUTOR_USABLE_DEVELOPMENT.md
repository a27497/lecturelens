# Bounded teaching Tutor development candidate

`p8-tutor-usable-v18-development` is an explicit opt-in candidate. It restores
source-anchored explanations, code examples and specific learner feedback that
v17's exact-excerpt publication language could not express. Socratic output remains
finite model-selected/controller-owned hint acts; it adds body/index questions.
It is experimental, Mock-only through `lecturelens_real_eval.tutor.usable_app:create_app`,
using `TUTOR_V18_DATABASE_URL` with an exclusive non-public schema and complete-v1
Java evidence. No default identity/registration is changed.

V18 bounds final answer/feedback at4096/1024 Unicode code points including labels
and full citations. Four900-character answer blocks and two384-character feedback
blocks fit those caps without truncation. The explicit smoke adapter allows4096
output tokens and reserves that allowance within existing runtime caps. PG/gateway/
Vue answer fields and polling protocol are unchanged.

Literal anchors and canonical citations establish binding, **not semantic support**.
The new explanation channel can still publish an unsupported interpretation with
a real anchor. V17's extract-only deterministic restriction is intentionally not
claimed for v18. Code is not executed; calculations check only bounded pure values.
Socratic hint relevance and course truth require judgment; opening a source can
reveal its solution. Real teaching quality is NOT_RUN.

See the [contract and capacity basis](../eval/tutor-usability-v18-v1/CONTRACT.md),
[development reference review](../eval/tutor-usability-v18-v1/reference-review-pack.json)
and [small smoke proposal](../eval/tutor-usability-v18-v1/SMOKE_PLAN.md). These are
known-course, author-exposed development materials, not independent human or holdout
acceptance. The smoke entry defaults to verification and cannot dispatch without
fresh exact-scope authorization. Full16 is a later decision.
