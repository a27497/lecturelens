# Security Policy

LectureLens is a learning and resume project. It documents and tests important security boundaries without claiming commercial multi-tenant service guarantees.

The current security focus is authentication, owner scope protection, sensitive information non-disclosure, dependency safety, and observability that avoids leaking secrets or business content.

## Supported Versions

Only the current `main` branch and local development version are considered supported.

Historical versions are not maintained. Security fixes should be applied to the current development line.

## Reporting a Vulnerability

If this repository is public, report suspected vulnerabilities through GitHub Issues or the repository security channel if it is enabled.

Do not include real API keys, tokens, passwords, private user data, uploaded files, raw prompts, raw model responses, object storage keys, local paths, or credentials in a public report.

For a useful report, include the affected feature, expected behavior, actual behavior, and safe reproduction steps using placeholder values only.

## Secrets and Credentials

- Do not commit `.env`.
- Do not commit API keys, access tokens, refresh tokens, passwords, access keys, secret keys, cookies, or private account credentials.
- `.env.example` must contain placeholders only.
- Runtime secrets must come from environment variables or local private configuration, not hard-coded source code or documentation.
- Logs, metrics, tracing context, screenshots, and docs must not contain real secrets.

## Authentication and Authorization

- Authentication currently uses JWT access tokens for protected APIs.
- Refresh tokens are stored as hashes and are rotated during refresh.
- Owner scope is enforced with the current user resolved on the server side from the Bearer access token.
- Upload, task, result, artifact, and AI call record access must not trust client-provided `userId`, `ownerId`, query parameters, request bodies, or spoofed owner headers.
- Current security hardening does not introduce full RBAC or a production multi-tenant authorization system.

## Data Protection Boundaries

API responses, frontend views, logs, metrics, tracing context, and documentation must not expose:

- `objectKey` or internal object storage keys.
- Local file paths or audio paths.
- Access tokens, refresh tokens, API keys, secrets, passwords, Authorization headers, or Cookie headers.
- Raw prompts, raw model responses, raw ASR payloads, subtitle full text in logs, or learning package full text in logs.
- `userId` in frontend views or external-facing resource views unless a future task explicitly changes the API contract.

## Upload Security

- Upload creation validates filename boundaries and rejects path-like or control-character input.
- Upload completion validates expected file size, MD5, allowed extensions, and basic video headers for supported formats.
- Chunk upload, missing chunk query, and complete all use owner scope based on the authenticated current user.
- Complete is based on the local chunk files that actually exist on disk; client claims alone are not treated as the source of truth.

## Observability Security

- Structured logs use sanitized, bounded error summaries and do not record request bodies, response bodies, sensitive headers, object storage keys, local paths, raw prompts, or raw responses.
- Metrics use low-cardinality tags only and must not include user identifiers, task identifiers, upload identifiers, filenames, object storage keys, local paths, tokens, secrets, or business content.
- Tracing context carries safe `traceId` and `requestId` values only. It must not include sensitive business data or credentials.
- Actuator exposure is limited to `health`, `info`, and `metrics`.

## Dependency Security

- GitHub Actions CI runs backend tests and frontend builds on `push` and `pull_request`.
- Dependabot checks Maven dependencies, npm dependencies, and GitHub Actions dependencies weekly.
- Dependabot is not configured for private registries, secrets, real reviewers, real assignees, or automatic merge.
- Dependency updates still require review and local verification before they are accepted.

## Docker / Local Security

- `.env` is local-only and must not be committed.
- Local MySQL, Redis, MinIO, and RocketMQ credentials are for local development only.
- Do not expose local Docker Compose services to the public internet.
- Do not publish MinIO buckets.
- Docker Compose starts infrastructure dependencies only; it is not a production deployment boundary for this project.

## Known Non-goals

- Full RBAC.
- Production multi-tenant SaaS isolation.
- Production-grade secret management.
- WAF, KMS, SIEM, or centralized security monitoring.
- Kubernetes security hardening.
- Automated dependency auto-merge.
- Production incident response or SLA policy.

## Security Checklist

Before committing changes:

- Check that no API key, token, password, cookie, private credential, or `.env` content is included.
- Check that responses, logs, metrics, tracing context, and docs do not expose `objectKey`, local paths, token values, raw prompts, or raw responses.
- Keep owner scope based on the server-side authenticated current user.
- Run the required tests or verification commands for the touched files.
- For dependency changes, review the diff and run the relevant backend or frontend verification before merging locally.
