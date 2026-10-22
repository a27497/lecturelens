# Continuous course learning workspace

PR4 builds on the existing video, transcript, Tutor, Study Agent and practice components. It changes page composition and navigation; it adds no execution engine, API or database migration. This is experimental UI behavior, not evidence of improved model teaching quality.

On desktop, course media and the original text share the left column while the active question, answer and feedback remain on the right. Evidence navigation checks the authoritative course revision before publishing a fresh transcript. On screens at or below 900px, reading and learning alternate without unmounting the current task. The source view carries the current question and a return action. Each practice question has its own existing answer/feedback component; changing the visible question keeps its same-page draft.

Tutor remains ordinary scoped course QA. Only the explicit **解释并出题** action starts a Study Run. The scope picker separates the next selection from the current record's frozen scope. Changing the next selection does not edit a saved Run. Saved answer revisions remain immutable; feedback identifies the answer version it actually assessed. Feedback may abstain, be disputed or remain unavailable. Recorded sources remain accessible when an abstaining feedback result includes them; this does not turn abstention into assessment or a mastery score.

## State and recovery

| State | Storage and recovery |
| --- | --- |
| Session, Run, artifact, answer revisions, feedback and feedback notes | Existing authorized server APIs; opening the Agent reads saved history. Reload restores the selected session's latest saved Run by the existing rules. History selectors still allow older records. |
| Course view, transcript view, playback coordinate and layout | Validated `view`, `text`, integer millisecond `at`, and optional `layout=classic` query parameters. Reload starts paused. The URL does not identify a saved question or persist the active question number. |
| Unsaved Tutor input, next goal, answer draft and feedback-note draft | Component memory for this page and course only. Evidence review and same-course panel/layout changes retain it. Reload, navigation away or course switch discards it. `KeepAlive` is not server persistence. |

Student answers and notes are not written to URLs or local storage. Read-only page entry, source review and history reads do not create a Session, start a Run or save an answer. A subordinate record error triggers an owning-course recheck. Confirmed 401/403/404 on that course read clears the cached panes and player; a missing individual record or transient error does not independently revoke the entire course. Old-course responses are fenced by request generations and component keys. The page cannot detect a server-side permission change before a subsequent read/event exposes it.

Engineering details remain available in **更多课程工具**, Trace, **模型设置与执行说明** and **保存、恢复与课程记录**. Model records remain lazy, owner-scoped and read-only.

## Compatibility and rollback

Existing view names, routes, scoped commands, signed media and Evidence contracts remain in use. **经典布局** adds `layout=classic`; **连续工作区** removes it. This provides a per-URL layout fallback without creating business state. Restoring the previous frontend artifact is the code rollback; there is no PR4 schema/data rollback. PR3's final repeatable migration and all earlier release constraints still apply independently. Do not delete or edit that migration as part of a frontend rollback.

See [PR4 verification](verification/vnext-pr4/README.md) for actual browser paths, baseline observations, fixtures, server verification and unverified release conditions.
