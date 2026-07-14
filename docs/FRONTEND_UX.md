# LectureLens Frontend UX

`FRONTEND-UX-REDESIGN-R1A` establishes the shared product shell and the visual baseline for the public, authentication, upload, and course-list routes. It does not change the course detail experience.

## Visual language

- Canvas: quiet warm gray (`--color-canvas`) with white primary surfaces.
- Emphasis: deep ink green for primary actions, active navigation, focus, and progress.
- Structure: light borders, low shadows, restrained 4–12 px radii, and generous whitespace.
- Typography: system-first Chinese and Latin font stack with clear size, weight, and spacing hierarchy.
- Components: Element Plus remains the control foundation; global tokens align buttons, inputs, progress, alerts, and radio filters with the product palette.
- Prohibited treatment: gradients, decorative dashboard tiles, oversized shadows, and equal-weight panels stacked without hierarchy.

## Route responsibilities

- `/`: short product introduction, one primary action, one secondary entry, and three concise steps.
- `/login`: login form, validation or request error, registration link, and home link.
- `/register`: registration form, password rule, validation or request error, login link, and home link.
- `/upload`: video selection, upload progress, pause/resume, collapsed technical details, post-upload original-video confirmation, and the action that starts course organization.
- `/tasks`: “我的课程” filters, course summaries, progress, open-course action, retry for failed work, and an explicit batch-management mode for soft deletion.
- `/tasks/:taskId`: unchanged in R1A and reserved for course detail content.

The global `AppShell` owns only the header, navigation, authentication area, background, content boundary, mobile menu, and `RouterView`. Route business content stays inside its page component.

## Responsive behavior

- Desktop content is capped at a shared readable width and keeps actions aligned with page headings.
- Mobile navigation collapses into an explicit menu and closes after route changes.
- Form panels become edge-aware without losing label, error, loading, or Enter-key behavior.
- Upload metrics and course metadata reflow to a single column; primary actions become full width.
- Technical identifiers and upload internals remain available through disclosure controls instead of occupying the primary reading path.

## Preserved behavior

- Router paths, authentication guards, redirect query handling, token behavior, and logout behavior.
- Registration and login validation, loading, error mapping, and Enter-key submission.
- Chunked upload, pause, resume, retry, progress, original-video playback, embedded subtitle probing, and course-task creation.
- Course fetching, status filtering, automatic refresh, detail navigation, task ID copy, and failed-task retry.

## R1A boundary

This phase does not modify APIs, stores, types, backend code, task-detail behavior, package dependencies, or production runtime configuration. Course-detail tabs and progressive result navigation belong to R1B.

## R1B course workspace

`FRONTEND-UX-REDESIGN-R1B` turns `/tasks/:taskId` into the Quiet Learning Workspace. The route has one goal: view and study one course. Its page structure is fixed to a course header, a persistent course-media area, and one active content module.

The primary workspace modules are:

- 概览
- 课程内容
- 学习资料
- 课程问答
- 下载
- 处理详情

Only the active primary module is mounted in the page DOM. `KeepAlive` preserves useful local state such as a question draft or search term without introducing another store. Changing `taskId` resets course-local state and returns the workspace to 概览.

课程内容 contains one active secondary view: 中文译文, 原文, or 时间轴. 学习资料 contains 摘要与重点, 课程章节, or 术语与问答. 处理详情 contains only 处理状态 or 模型调用. Technical fields and model usage stay outside the default learning path. The frontend no longer exposes keyframe images, OCR/visual panels, or a Video Segment user interface.

On desktop, the video and status column remains sticky beside the active content surface. Tablet and mobile layouts stack the video above the content, disable sticky positioning, and allow the course navigation itself to scroll without creating page-level horizontal overflow.

Course detail never requests keyframe image blobs. Chapter generation, course QA, artifact download, retry, and cancellation remain explicit user actions.

The route keeps one `main` landmark in `TaskDetailView`. Workspace child components use `section`, `article`, `aside`, `nav`, and `div`. Primary and secondary navigation expose semantic current states, and chapter and timeline jumps use keyboard-operable buttons.

## PRODUCT-POLISH-R1 batch management

The course list remains unchanged by default. “批量管理” reveals accessible checkboxes only when requested. `SUCCEEDED`, `FAILED`, and `CANCELED` courses can be selected; all other states are disabled with “处理中课程请先取消处理”. Selection is limited to the currently loaded and filtered list, capped at 100 tasks, cleared on filter changes, and reconciled during silent refresh so hidden, missing, or newly non-terminal tasks cannot remain selected.

The management toolbar wraps on narrow screens and shows the selected count, “全选当前列表”, the dangerous “删除所选” action, and “退出批量管理”. Confirmation cancellation sends no request. Confirmation sends one `POST /api/tasks/batch-delete` body containing only deduplicated `taskIds`; loading disables repeated submission, selection changes, filter changes, and exit. Success leaves batch mode and reloads the list; failure keeps the current valid selection. The 390 px layout has no fixed-width control that creates page-level horizontal overflow.
