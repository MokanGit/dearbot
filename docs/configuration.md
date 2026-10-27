# Configuration

Copy `.env.example` for local work. Production operators should start from `deploy/runtime.cv.env.example` and store the resulting file outside Git with restrictive filesystem permissions.

## Runtime and network

- `ENV`: `development`, `test`, or `production`.
- `BASE_URL`: canonical browser origin used in generated profile links.
- `API_BASE_URL`: canonical backend origin.
- `NEXT_PUBLIC_API_URL`: browser-visible backend origin.
- `CORS_ORIGINS`: comma-separated browser origins allowed to call FastAPI.
- `ALLOWED_HOSTS`: comma-separated host header allowlist.
- `TRUST_PROXY_HEADERS`: honor `X-Forwarded-For`/`X-Real-IP`; enable only when direct backend access is blocked and the proxy overwrites these headers.

## Candidate identity

`CANDIDATE_NAME`, `CANDIDATE_HEADLINE`, `CANDIDATE_SUMMARY`, and `CANDIDATE_CONTACT_LINE` control generated documents. Their `NEXT_PUBLIC_*` counterparts control browser-visible labels.

These values are public content, not secrets. Keep private notes in canonical documents classified as internal.

## Models

Set `LLM_PROVIDER` to `mock`, `gemini`, or `openai`. Provider keys are server-only secrets. Model identifiers are configuration because provider availability changes independently of DearBot releases.

Mock mode is for development and automated tests. Production does not silently fall back to synthetic mock answers when a configured provider is unavailable.

## Storage and ingestion

- `DATABASE_URL`: SQLAlchemy-compatible SQLite or PostgreSQL connection.
- `LOCAL_SYNC_DIR`: private Markdown evidence directory.
- `GENERATED_CVS_DIR`: generated document directory.

Local Markdown is the supported beginner source. Google Drive variables and Obsidian-based generation belong to [advanced integrations](advanced-integrations.md) and are not required for onboarding.

## Observability

LangSmith tracing is disabled by default. Enabling it may send prompts, job descriptions, evidence excerpts, and generated answers to an external processor. Confirm the data-processing basis and retention settings first.

## Authentication

See [authentication.md](authentication.md). `AUTH_MODE=disabled` is intentionally limited to development and tests.
