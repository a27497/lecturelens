# Course video and transcript position

Implemented on main through PR1; not deployed. This improves navigation and continuity, not Agent task quality.

## Behavior

- The player reports milliseconds at most four times per second during playback, with immediate final seek/pause positions. The timeline highlights the actual source subtitle interval. Ranges are `[start, end)`; gaps and empty intervals have no active row. Overlaps select the latest start, then the first input row for equal starts.
- Time lookup is indexed once per transcript, with binary lookup during playback. Embedded VTT subtitles have an independent index; they are never matched to course subtitles by array position. Translations require matching segment IDs **and** identical time bounds. Full translations remain full text.
- Timeline following is initially enabled. Wheel, touch, pointer or navigation-key interaction and search pause it. The resume button clears search and returns to the playing passage. Automatic scrolling is confined to the transcript container and stops while the panel is hidden.
- Existing transcript, chapter, Tutor and practice evidence actions use the shared seek implementation. A request received before metadata waits for the player, clamps to duration and preserves paused/playing intent. Link refresh preserves position and resumes only a previously playing video; a document reload starts paused.
- Evidence review opens the source timeline beside the task in the continuous desktop workspace, or in a reading view on narrow screens. `layout=classic` retains the source-above-task arrangement. It does not replace the question, input, saved answer, answer revision, feedback or feedback-note editor. The return button restores focus and page position. Tutor, explanation and feedback links retain the canonical Evidence ID and frozen course revision. Before navigating, the frontend brackets a fresh transcript read with two authorized revision reads through the existing Evidence index-status endpoint, without requiring Study readiness for already available course sources. It publishes the checked transcript and position together, superseding older pending result loads. Changed/missing revisions or an unavailable check stop navigation with a notice and preserve learning state; late responses are ignored after another seek, manual player seeking, a view change or a course change. Artifact edit revisions are never used as source revisions. Canonical Evidence identifiers, ranges, revisions and server authorization remain under existing contracts; a URL time coordinate is not an Evidence identity or a new authorization.
- The task URL accepts `view`, `text`, optional `layout=classic` and integer millisecond `at` (0–604800000). Unknown/duplicate view parameters and invalid times fall back safely. Explicit workspace changes create history; playback replaces the current entry approximately every 1.5 seconds. A reload can therefore lag playback by this interval. No media tokens, questions, goals or answers are added to the URL or local storage.
- Each course owns a fresh component cache and player. Back/forward applies that history entry's coordinate; entering a bare course URL starts at zero. Unsaved input survives evidence review and same-course panel switches, not document reload or switching courses. Saved learning records continue to restore through existing server reads. Navigation never starts a Run.
- No subtitles and media errors leave other course material readable. The upload preview is keyed by upload identity, so position is retained only across link refresh for the same upload.

## Verification

Unit tests cover interval boundaries, nested overlaps, invalid/empty ranges, a 10,000-range oracle comparison, pending seeks, throttling, duration clamping, follow control, hidden views and translation alignment. Existing Agent, feedback and other frontend tests remain part of the full suite.

`frontend/tests/browser/coursePosition.mjs` serves an isolated production build on a random loopback port. Business APIs, Tutor answers and saved learning records are **fixtures**. Only local requests are allowed; unknown study commands fail. Video decode, playback, seeking, DOM layout, scrolling, history, refresh, focus and viewport behavior use real Chromium and real H.264 files. These checks do not establish backend authorization, real-provider quality, production media compatibility or real long-course acceptance.

Build into a directory that is not mounted by a running gateway. Wrap long checks with `scripts/dev/run_check.py` where that supervisor is available in the development checkout. A disk-gated checkout can be copied with the unchanged supervisor to a separate filesystem and checked there; keep sources, dependencies, media, logs and build output together on that filesystem.

Example commands from `frontend/` (run under the supervisor):

```bash
npm ci
npm run test:unit
npm run type-check
npm audit
npm run build -- --outDir /isolated/pr1/dist

ffmpeg -nostdin -f lavfi -i testsrc2=size=320x180:rate=12 -t 12 \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart /isolated/pr1/short.mp4
ffmpeg -nostdin -f lavfi -i testsrc2=size=64x64:rate=1 -t 3900 \
  -c:v libx264 -g 10 -pix_fmt yuv420p -movflags +faststart /isolated/pr1/long.mp4

npm run test:browser -- --dist /isolated/pr1/dist \
  --media /isolated/pr1/short.mp4 --long /isolated/pr1/long.mp4 \
  --chromium /path/to/chrome --output /isolated/pr1/browser-results
```

`--chromium` is optional if a Playwright Chromium installation is available. `--baseline` records the same URL's initial player/workspace state against a baseline build. `--classic` exercises the original layout fallback. `--review` runs nine focused source-version and navigation-race scenarios. `--only` runs a matching named scenario for debugging. Keep generated media, screenshots and browser output out of Git.

## Release and rollback

This change requires no service configuration, backend change or database migration. Release only after review and separately authorized deployment. Before release, verify a complete real long course, authenticated backend evidence access/version changes, expired authorization and supported desktop/mobile browsers. Revert the frontend commits or restore the prior frontend artifact through the normal release process to roll back; existing learning records require no conversion.
