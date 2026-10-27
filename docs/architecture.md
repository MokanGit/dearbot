# Architecture

DearBot is a small, single-candidate application composed of a Next.js frontend and a FastAPI backend.

## Components

- **Next.js frontend**: landing page, administrative workspace, public application profile, QR-code presentation view, and WebMCP integration.
- **FastAPI backend**: application lifecycle, document ingestion, evidence selection, generation, public profile APIs, MCP, telemetry, and cleanup.
- **Database**: SQLite by default; PostgreSQL can be supplied through `DATABASE_URL`.
- **Evidence storage**: reviewed local Markdown documents by default, with optional advanced source integrations.
- **Model provider**: deterministic mock mode for development, with optional Gemini or OpenAI runtime providers.
- **Reverse proxy**: expected in production for TLS, request limits, security headers, routing, and network separation.

## Trust boundaries

```text
Internet visitor ── public token ──> public FastAPI routes
Administrator ── Entra access token ──> admin FastAPI routes
FastAPI ── provider credentials ──> model and document services
FastAPI ── local credentials ──> database and private evidence
```

Public application tokens are bearer capabilities. They expose only the application profile and documents deliberately associated with that application; they do not grant administrative access.

The browser is untrusted. Client-side route visibility and identity display are user experience features, not authorization boundaries. Administrative authorization is enforced by FastAPI dependencies.

## Data flow

1. The operator imports canonical evidence.
2. DearBot classifies documents as internal by default; public classification must be explicit.
3. A job description supplies relevance and vocabulary, not new career facts.
4. Generated content is stored with the application record and an opaque public token.
5. Public Q&A receives only approved evidence plus the application context required to answer the question.
6. Revocation disables the profile; cleanup removes associated telemetry and generated material according to the retention policy.

## Deliberate limitations

DearBot does not currently provide tenant isolation, user registration, billing, collaborative editing, or an authorization model for multiple unrelated candidates. Deploy one trusted instance per candidate or add those boundaries before broader use.
