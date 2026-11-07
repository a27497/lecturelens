# v13 claim grounding development experiment

An explicit, unregistered development candidate adds a source-only context fix and
general claim-grounding instructions to v12. Product defaults are unchanged.
[The cause report](CAUSE_REPORT.md) distinguishes proven context/output facts from
unknown model reasoning and preserves the historical v12 scores separately.

The learner still asks bounded course questions; the model chooses up to two
searches and then an answer, guiding question or clean abstention. The stored
outcome retains actual history, observations, selected source IDs, proposed tools,
answer and budget/stop state. Neither an existing citation ID nor Mock completion
proves factual support. No semantic reviewer, automatic citation attachment,
new tool, retry or repair opportunity was added.

[The frozen plan](run-plan.json) selects four complete new development sessions,
16 positions, on two previously unevaluated complete episodes from the existing
Python and ecology spreadsheet courses. Source commits, original Markdown,
licenses, references and [pre-result source review](CONTENT_REVIEW.json) are
retained. No SQL holdout is loaded. [Grading rules](grading-rules.json) freeze the
same acceptance tolerances as the previous sixteen-position trial, with explicit
within-answer deduplication of semantic restatements. These are public known
courses, not unseen-course generalization.

`trial_run.py` is a narrowly adapted copy of the frozen v12 runner. Identity,
source, plan and runtime selection change; its accounting and local/global failure
classification remain the same. The parent contract and all historic data remain
hash-verified. `v13_contract.py` refuses a stale/missing/mismatched manifest or
frozen input before output/DB/transport creation. Preparation only:

```bash
PYTHONPATH=agent-service/src agent-service/.venv/bin/python \
  eval/tutor-v13-grounding-v1/trial_run.py \
  --agent p8-tutor-claim-grounding-v13-development --model deepseek-flash
```

No candidate results existed when `freeze-lock.json` was written. The new-sample
Mock checks occur after that freeze and test mechanics only. See
[the execution sheet](EXECUTION_SHEET.md) for the authorized single real trial;
[the final report](REAL_REPORT.md) records its actual version, quality, costs and
closure when execution/review are complete.
