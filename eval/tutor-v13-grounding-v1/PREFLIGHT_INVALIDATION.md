# First new-sample freeze invalidated before paid execution

**DO NOT EXECUTE this first sample bundle as a real trial.** No paid request or
real candidate result exists. The initial zero-cost regression passed 273 tests,
but the subsequent original-Markdown review found spreadsheet reference locators
had incorrectly used web-rendered line numbers. Source bytes, task texts,
reference points and thresholds were not changed to improve any result.

The source review in `CONTENT_REVIEW.json` was therefore overconfident about
reference locations; it is retained as a failed authoring artifact, not accepted
source validation. The first `freeze-lock.json`, candidate and all evidence remain
unchanged. An additive locator bundle was saved under
`../tutor-v13-grounding-v2/`, retaining the same candidate behavior and questions.
Its final check failed during collection because the newly added test omitted a
`pytest` import. Per the user's stop gate, no paid validation followed and no
further fix was attempted. Both bundles are **blocked for live use**.

See [the stage report](STAGE_REPORT.md), which records the authoring/preflight
mistakes and the distinction between passed mechanism tests and unperformed
real-model quality validation.
