# LectureLens Test Plan

This document defines the current test strategy for LectureLens. It is a project-level verification guide, not a hosted-service QA certification.

## Test Goals

- Keep authentication, upload, task orchestration, AI provider abstractions, subtitle persistence, learning package generation, artifact generation, result overview, security, and observability behavior regression-testable.
- Keep automated tests runnable without real external APIs or live infrastructure services.
- Make CI boundaries explicit: backend tests and frontend build must pass, but CI does not deploy, publish artifacts, or connect to real MySQL, Redis, RocketMQ, MinIO, ASR, LLM, or FFmpeg services.
- Keep security assertions source-grounded: tests and manual checks must not expose tokens, secrets, API keys, object storage keys, local paths, raw prompts, raw responses, subtitle full text in logs, or learning package full text in logs.

## Test Layers

### Backend Unit Tests

Scope:

- Pure domain rules and validators.
- Token, filename, object key, state machine, formatter, parser, sanitizer, metrics tag, and tracing context behavior.
- Error normalization and sensitive information sanitization.

Examples in the current tree include tests for auth services, upload validators, state machine rules, SRT/VTT/Markdown/JSON formatters, response parsers, safe log sanitizing, tracing, and security headers.

### Backend Service Tests

Scope:

- Application services that coordinate mappers, providers, storage abstractions, Redis abstractions, MQ abstractions, and state transitions.
- Owner scope behavior for upload sessions, tasks, subtitles, learning packages, artifacts, AI call records, and result overview.
- Failure handling and sanitized error summaries.

External dependencies must be represented with fake clients, mock providers, in-memory collaborators, or disabled-mode configuration unless a future TODO explicitly requires live integration testing.

### Backend Controller / API Tests

Scope:

- Request validation.
- Authentication boundary and Bearer access token handling.
- API response shape through `ApiResponse<T>`.
- Owner scope enforcement.
- Security response headers.
- Actuator exposure boundary.

Controller tests should verify that responses do not expose `userId`, `objectKey`, local paths, access tokens, refresh tokens, API keys, secrets, Authorization headers, Cookie headers, raw prompts, or raw responses.

### Mapper / Persistence Tests

Scope:

- Flyway migration availability.
- Mapper CRUD and query behavior for current tables.
- Owner scope indexes and stable ordering where relevant.
- Persistence services that use `taskId + userId`, `uploadId + userId`, or `taskId + userId + language` boundaries.

These tests must not require a developer to start real MySQL manually as a normal unit-test prerequisite.

### Frontend Build / Type Check Boundary

Current frontend verification is build-oriented:

- `npm run build` runs `vue-tsc -b` and `vite build`.
- This covers TypeScript and Vue compile-time regressions.
- There is no separate frontend unit-test suite in the current project state.

Frontend verification must not require a real backend, real Docker Compose services, or real AI provider credentials.

### CI Tests

GitHub Actions workflow `CI` has two jobs:

- `backend-test`: runs backend Maven Wrapper tests on Ubuntu with Java 21.
- `frontend-build`: installs frontend dependencies with `npm ci` and runs `npm run build` on Node.js 24.

CI does not deploy, publish Docker images, push artifacts, configure secrets, or connect to real MySQL, Redis, RocketMQ, MinIO, ASR, LLM, or FFmpeg services.

### Manual Verification

Manual verification is for local smoke checks and demonstration readiness. It is not a replacement for automated tests and is not required for docs-only changes.

Use manual checks only when the touched task requires runtime behavior validation or when preparing a demo.

## Commands

### Backend Tests

Windows PowerShell:

```powershell
cd backend
.\mvnw.cmd test
```

Linux / GitHub Actions:

```bash
cd backend
./mvnw test
```

### Frontend Build

```powershell
cd frontend
npm run build
```

When dependencies have not been installed locally:

```powershell
cd frontend
npm install
npm run build
```

CI uses `npm ci` because `frontend/package-lock.json` exists.

### Documentation-Only Verification

For docs-only tasks that do not change code, tests, package files, Maven files, CI, Docker Compose, or application configuration:

```powershell
git diff --check
git status --short
```

## External Dependency Testing Principles

- ASR and LLM tests must use fake clients, mock providers, disabled-mode configuration, or local parser/validator tests.
- Tests must not call real OpenAI-compatible endpoints, SiliconFlow-compatible endpoints, LangChain4j remote services, or any external LLM / ASR service.
- Tests must not require real API keys.
- FFmpeg behavior should be tested through process abstractions, fake executors, validation tests, or small controlled fixtures rather than treating a real FFmpeg runtime as a unit-test prerequisite.
- MinIO tests should use storage abstractions or fake storage where possible; real MinIO is not required for the default test suite.
- Redis tests should cover enabled, disabled, fallback, and fail-open behavior without requiring a developer to start real Redis manually.
- RocketMQ producer, consumer, and runner boundary tests should use mocks or configuration-controlled no-op behavior unless a future task explicitly introduces live integration testing.
- Docker Compose is useful for local infrastructure smoke checks, but it is not a default automated test dependency.

## Key Regression Areas

### Auth

- Registration stores BCrypt password hashes and does not issue tokens.
- Login issues JWT access tokens.
- Refresh token flow stores hash values and rotates refresh tokens.
- `/api/me` uses Bearer access tokens only.
- Invalid, expired, malformed, or missing tokens fail safely.

### Upload

- Upload session creation validates file metadata.
- Chunk upload persists chunk data through the current local staging behavior.
- Missing chunk query uses Redis short state when available and falls back to local staging facts.
- Complete validates chunk completeness, file size, MD5, allowed extension, and basic video headers.
- Upload owner scope is enforced for session, chunk, missing, and complete operations.
- Upload responses do not expose `objectKey`, local paths, or `userId`.

### Task

- Task creation validates authenticated owner access to an uploaded session.
- Task creation only creates task state and sends the configured analysis message boundary; it does not run FFmpeg, ASR, LLM, LangChain4j, subtitle generation, learning package generation, or artifact generation in the HTTP request thread.
- Task list and detail APIs return only the current user's tasks.
- SSE stream sends snapshot, progress, heartbeat, and terminal events within the current safe response contract.
- Retry and cancel enforce legal state transitions, retry limits, owner scope, and safe MQ message boundaries.
- State machine tests cover legal and illegal transitions.

### AI Provider Abstractions

- ASR and LLM providers validate requests and parse responses without real network calls.
- Disabled providers do not create live external calls.
- Provider errors are sanitized and bounded.
- LangChain4j integration remains disabled unless explicitly configured.

### Subtitle / Translation / Learning Package

- Subtitle persistence overwrites and queries by `taskId + userId`.
- Translation persistence overwrites and queries by `taskId + userId + targetLanguage`.
- Learning package persistence validates required structured fields and returns views without `userId`.
- Parser tests cover valid, invalid, and malformed model output.

### Artifacts

- SRT, VTT, Markdown, and JSON generation sanitize content and reject sensitive text.
- Artifact metadata is saved by owner scope.
- Artifact views do not expose `objectKey` or local paths.
- Fake storage is preferred for automated tests.

### Result Overview

- Result overview checks task owner scope before aggregating subtitle, translation, learning package, artifact, and AI call record views.
- Empty result sections return stable empty arrays or `null` where documented.
- Responses do not expose internal identifiers or sensitive storage fields.

### AI Call Records

- Call records store safe metadata only.
- Start, success, and failure updates use owner scope.
- Failure summaries are sanitized and length-limited.
- Views do not expose `userId`, raw prompts, raw responses, paths, object keys, headers, keys, tokens, or secrets.

### Observability

- Structured logs include safe request, task, MQ, Runner, and error fields only.
- Metrics use low-cardinality tags and do not include user IDs, task IDs, upload IDs, object keys, paths, tokens, secrets, raw prompts, raw responses, subtitles, or learning package content.
- Tracing context only carries safe `traceId` and `requestId` values.
- Actuator only exposes `health`, `info`, and `metrics`.

## Security Test Checklist

- Unauthenticated protected API requests fail.
- Cross-user access fails without revealing whether the resource exists.
- Client-supplied `userId`, `ownerId`, query parameters, request bodies, and spoofed owner headers are ignored for owner decisions.
- API views do not expose `userId`, `objectKey`, local paths, access tokens, refresh tokens, API keys, secrets, Authorization headers, Cookie headers, raw prompts, or raw responses.
- Logs, metrics, and tracing context do not leak tokens, secrets, API keys, object keys, local paths, raw prompts, raw responses, subtitle full text, or learning package full text.
- Security headers are present on normal API, Actuator, and protected-error responses.

## Manual Verification Checklist

Use this list for local smoke checks when runtime validation is needed:

- Copy `.env.example` to `.env` and keep `.env` untracked.
- Start Docker Desktop or Docker Engine only when infrastructure smoke checks are required.
- Run `docker compose up -d` for MySQL, Redis, MinIO, and RocketMQ infrastructure.
- Run `docker compose ps` and targeted `docker compose logs -f <service>` for infrastructure checks.
- Start the backend with Java 21 and Maven Wrapper.
- Start the frontend with Node.js 24 and npm.
- Register or log in with local test credentials.
- Exercise the upload flow through the frontend upload page.
- Create an analysis task only within the current implemented task boundary.
- View task list, task detail, SSE progress, and result overview pages.
- Check Actuator `health`, `info`, and `metrics`.
- Confirm no UI, API response, log, metric, trace, or screenshot exposes secrets, object keys, local paths, raw prompts, or raw responses.

The current Runner still does not execute the full real AI Pipeline. Do not treat a local smoke test as proof that FFmpeg, ASR, LLM, LangChain4j, and complete artifact production are wired end to end.

## Known Warnings

These warnings may appear during local verification and do not block success when the command exits with code `0`:

- Mockito dynamic agent warning during backend tests.
- Frontend build warnings related to Rolldown annotations or chunk size.

If any warning is accompanied by a non-zero exit code, failed tests, failed type checking, or missing build output, treat the verification as failed.

## Pre-Commit Checklist

- Required backend tests pass when backend code, backend tests, Maven files, or backend configuration are changed.
- Required frontend build passes when frontend code, package files, or frontend configuration are changed.
- `git diff --check` passes.
- `git diff --cached --check` passes before committing.
- The staged file list matches the current TODO scope.
- `.env` is not staged.
- No real API key, token, password, cookie, access key, secret key, private account credential, object storage key, local path, raw prompt, or raw response is staged.
