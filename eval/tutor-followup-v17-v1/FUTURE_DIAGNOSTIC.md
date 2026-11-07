# One real diagnostic proposal — BLOCKED / NOT_RUN

No current paid authorization exists. Do not dispatch, expand or activate a product
worker. The candidate entry/protocol is frozen, but independent reference review
and dispatch-valid model/price preflight receipts are missing. This is a candidate preparation,
not a final-ready or independently reviewed acceptance bundle.

## Exact version and limits

- Identity: `p8-tutor-verified-v17-development`; candidate manifest SHA-256
  `287cde807fde4933ddc2ced79659f045d43c545f6f4432ab21c2d2f9ed5fb815`.
- Actual code commit: `3b9bae4859af243dc6b77bf0fa5ba6c4b0221c31`;
  freeze commit: `f573853`. The approved execution receipt must additionally bind
  the exact clean final delivery HEAD, not a branch name. Entry checks all source
  roots against the code commit and every manifest file; execution.json records
  both actual HEAD and code commit. No hidden working-tree patch is accepted.
- Entry: `scripts/dev/run_tutor_diagnostic_v17.py`; implementation:
  `agent-service/src/lecturelens_real_eval/tutor/guarded_diagnostic.py`.
  Execution/artifact/stop contract: `execution-protocol.json`. Default mode is
  verify-only: no DB, transport or credential lookup. Product factory stays Mock.
- Exact requested API model ID **`deepseek-flash`**, route
  `https://api.deepseek.com/chat/completions`, temperature0, thinking disabled,
  output1200, concurrency1, retries0, reviewer0, embeddings0. This is a requested
  alias; current availability/pricing and an immutable supplier backend are
  unverified at freeze. The later [public-document check](OFFICIAL_PREFLIGHT.md) records published compatibility, not account access or immutable request identity. Unexpected returned model stops the whole batch; no substitution.
- Packet SHA-256: `e413ce3b8f9786b1cebd860fb2c4b36961cfeac2e2d2f53e69461eb6f233f0b1`.
- Exactly the16 ordered positions in `sample-candidate.json`, inherited questions,
  required points and strict gates unchanged. **Development-exposed known courses,
  not holdout**: Codex inspected obligations during implementation and matching
  numeric unit fixtures exist. No candidate has executed the packet itself.
  Its inherited after-freeze authorship label refers to the original v15 packet;
  these are not fresh questions selected after the v17 freeze.
- Hard admission limit **80 egress attempts**, including repairs/failures; runtime
  turn/session/deadline/byte limits remain unchanged. **US$0.70** is the hard local
  reserved-plus-settled liability ceiling, not a supplier invoice guarantee.
  Unknown usage retains full reservation and stops. No rerun/resume into a new
  budget; one-use run ID is durably claimed before setup/network. Higher price,
  unavailable configuration or inadequate conservative liability coverage stops
  for a new proposal. A separate documentary price lookup is retained; no model request or dispatch-valid receipt is performed/issued here.

## Required external inputs

1. **Independent source/reference review.** A reviewer who did not author the
   questions/runtime must inspect REFERENCE_REVIEW.md and the full original
   source, then return per-position obligation/ambiguity/scoring dispositions.
   Preserve reviewer identity, declared authoring involvement and disagreements
   before any adjudication. The same Codex author's second pass is explicitly
   nonblind and not independent human review. No reviewer has been assigned.
   Do not weaken feedback, targeted hint, required conditions or full coverage to
   compensate for v17's narrower publication language. If changes are necessary,
   create separately versioned packet/entry locks; never edit these frozen files.
2. **Fresh explicit grant.** The nonexecuting authorization-template.json has
   `authorized=false` and null bindings. A separate later grant must approve
   `ONE_V17_DIAGNOSTIC_NO_RETRY_NO_EXPANSION`, exact candidate/packet/clean HEAD,
   model,80 requests,700000000 nano-USD, expiry and one new run ID. All old grants
   are expired. The entry validates declared receipt fields; it cannot itself
   authenticate a person's independence or replace actual approval.
3. **Current official model/price preflight.** Under that later authorization,
   verify alias/configuration without a trial model request and record an official
   source and UTC timestamp within24h. Frozen local rates are conservative300 /
   1200 nano-USD per input/output token, ignoring cache discounts. Admission
   requires a declaration that these cover current no-cache peak prices. If not,
   stop; do not silently substitute rates or increase the ceiling.

Live admission also requires `LECTURELENS_REAL_EVAL=1`, an isolated disposable
acceptance PostgreSQL on the explicit test loopback port, a fresh private output
directory and existing approved credential provisioning. No credential is read,
created, printed or copied in this phase. Do not put credentials in shell args
or receipts. Receipts go in ignored private storage, not into the frozen bundle.

The eventual live invocation has this form, **not executed**:

```sh
agent-service/.venv/bin/python scripts/dev/run_tutor_diagnostic_v17.py --mode live --output .data/APPROVED_FRESH_OUTPUT --authorization APPROVED_GRANT.json --reference-review APPROVED_REFERENCE_RECEIPT.json --pricing CURRENT_PRICE_RECEIPT.json
```

Do not use the offline socket fence for a paid invocation and silently infer
network permission. Actual network/credential use belongs to the later approved
environment/preflight; this proposal grants none.

## Stopping, artifacts and judgment

Format/support/context-capacity failures close that session and preserve later
positions as skips; independent sessions may continue. Provider transport/schema,
unknown usage/outcome, model mismatch, fabricated/stale authority, ledger divergence
or budget failure stops the whole batch. No automatic transport retry or failed
candidate replacement. Engineering interruptions export state and mark unobserved
positions distinctly. Live ledger/schema and the one-use claim are retained;
unknown calls are never resent. Mock exports and drops only its own schema.

Artifacts: execution.json, owner.json, summary.json, all16 outcomes, runtime.json,
calls.jsonl, mirrored ledger.jsonl and numbered request/response/capture records.
Body files are bounded decoded HTTP entity bytes before JSON parsing, not TLS
frames. Known request authorization secrets are redacted, including decoded JSON
escapes; redaction may require JSON reencoding and is explicitly marked. Headers
and exception text are not retained. This is not an arbitrary-secret/PII detector;
only frozen public sources and synthetic learner text are permitted. Prior
historical parsed-response replay remains **reconstructed**, never original bytes.

Keep every original gate:16 complete/no failures/skips/missing for mechanics;
correct≥14/16 and≥7/8 per course; all3 critical/4 refusals/2 Socratic/2 feedback/
2 clarifications; contextual≥9/10; citation support≥0.95, claim coverage≥0.90 and
full answerable coverage≥10/12. Include uncertain and optional substantive
assertions/pairs and all scheduled positions. Calculation validity, exact text
membership, controller wording and Mock success do not establish these gates.

Independent human output ratings/agreement are a separate unperformed activity.
A03 misleading crops, formula relevance and generic hint/feedback limitations
remain visible to raters. No code change or gold adjustment follows output without
a separate version and review. After the one approved diagnostic, stop regardless
of result. Real quality improvement, cost optimization, human agreement, SQL,
scaling and learning effects remain NOT_RUN in this phase.
