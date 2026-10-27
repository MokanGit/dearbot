# DearBot

> Dear Hiring Bot,
>
> Since you don't read our applications, we've stopped writing them.
>
> Sincerely,
>
> Another Bot.

Open-source CV and cover-letter generation for the age of automated recruitment.

DearBot turns a canonical, evidence-backed career history into role-specific application packages and optional AI-readable profiles. Its central rule is deliberately boring: the job description may change what gets emphasized, but it may not change the facts.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg)](backend)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black.svg)](frontend)

## Status

DearBot is being prepared for publication in a new repository at `MokanGit/dearbot`. This repository remains private during cleanup and security review. The project is intended for a single candidate or trusted household deployment; it is not a multi-tenant recruitment service.

The included `Sample Candidate` data is fictional. Real CVs, application packages, databases, credentials, and synchronized documents are intentionally excluded from version control.

## What it does

1. Ingests a canonical Markdown CV or evidence bank locally, with optional advanced source integrations.
2. Reads a job description supplied as text or a URL.
3. Generates a tailored CV, cover letter, fit summary, and interview questions.
4. Creates an optional tokenized profile for human visitors and compatible agents.
5. Links material claims back to source documents and refuses unsupported claims.

The public profile supports ordinary HTML, JSON discovery, REST Q&A, MCP, and browser-based WebMCP. Administrative operations are kept on a separate authenticated route.

## Local quickstart

Requirements: Docker with Compose.

```bash
cp .env.example .env
./local_docker.sh
```

Open:

- Application: <http://localhost:3000>
- Admin workspace: <http://localhost:3000/admin>
- Development API documentation: <http://localhost:8000/docs>

The example configuration uses the deterministic `mock` provider and `AUTH_MODE=disabled`, so local development needs neither cloud credentials nor Microsoft Entra. Disabled authentication is rejected in production.

### First-time candidate setup

Use the beginner onboarding package to turn existing career documents into a private, evidence-grounded master CV:

> Read `skills/dearbot-onboard/SKILL.md` and guide me through DearBot beginner onboarding using only the career documents I explicitly provide.

The beginner path uses local Markdown and does not configure Google Drive or Obsidian. See [Beginner onboarding](docs/onboarding.md) for the workflow and privacy boundaries.

For production or migration work, ask an AI coding tool to read `skills/dearbot-deploy/SKILL.md`. The deployment skill separates DearBot's portable two-container runtime from the SSH, Caddy, Tailscale, storage-path, and container-name assumptions inherited from the current Hetzner installation.

For a non-Docker setup, see [Development](docs/development.md).

## Configuration

Configuration is supplied through environment variables. Start with [.env.example](.env.example) and see [Configuration](docs/configuration.md) for the full grouping and production rules.

The most important settings are:

| Variable | Purpose | Local default |
| --- | --- | --- |
| `ENV` | Runtime safety profile | `development` |
| `AUTH_MODE` | Backend admin authentication | `disabled` |
| `NEXT_PUBLIC_AUTH_MODE` | Matching frontend auth mode | `disabled` |
| `LLM_PROVIDER` | `mock`, `gemini`, or `openai` | `mock` |
| `CANDIDATE_NAME` | Candidate identity used in generated material | `Sample Candidate` |
| `DATABASE_URL` | SQLite or PostgreSQL connection | local SQLite |

Production requires `AUTH_MODE=entra` and a correctly configured DearBot API scope. See [Authentication](docs/authentication.md).

## Data and evidence

- `backend/data/synced_docs/` contains local canonical evidence and is ignored by Git.
- `backend/data/applications/` and `backend/data/generated_cvs/` contain runtime output and are ignored by Git.
- Only documents explicitly marked public are made available to public profile responses.
- Application notes remain private and are not added to the public evidence context.
- Generated profile tokens can be revoked and their telemetry purged.

Read [Data and privacy](docs/data-privacy.md) before importing real career material or enabling tracing.

## Authentication

DearBot has two currently supported modes:

- `disabled`: development and tests only. The frontend skips sign-in and the backend issues a local development principal.
- `entra`: production-capable Microsoft Entra authentication using an access token issued for the DearBot API.

Entra tokens must have the configured API audience and `admin.access` scope or role. Microsoft Graph tokens, ID tokens, and client-side email allowlists are not accepted as authorization.

## Architecture

```text
Browser
  ├─ public profile ───────────────┐
  └─ admin workspace + access token│
                                   ▼
                            Next.js frontend
                                   │
                                   ▼
                            FastAPI backend
                      ┌────────────┼────────────┐
                      ▼            ▼            ▼
                 SQLite/Postgres  LLM API   Optional sources
                      │
                      ▼
             evidence + applications
```

See [Architecture](docs/architecture.md) for trust boundaries and request flows.

## Development and verification

Backend:

```bash
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt
pytest backend/tests
```

Frontend:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm build
```

The test suite covers evidence isolation, unsupported-claim refusal, application separation, authentication, rate limits, data lifecycle behavior, PDF packaging, MCP, WebMCP, and concurrent presentation traffic.

## Deployment

The repository includes Docker images, a production Compose example, and a Caddy configuration suitable for a small self-hosted deployment. Hetzner remains a supported deployment target, but no provider-specific credentials or infrastructure state belong in this repository.

See [Deployment](docs/deployment.md) and the [publication checklist](docs/publication-checklist.md).

## Project documentation

- [Architecture](docs/architecture.md)
- [Authentication](docs/authentication.md)
- [Configuration](docs/configuration.md)
- [Beginner onboarding](docs/onboarding.md)
- [Advanced integrations](docs/advanced-integrations.md)
- [Development](docs/development.md)
- [Deployment](docs/deployment.md)
- [Data and privacy](docs/data-privacy.md)
- [Publication checklist](docs/publication-checklist.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)

## License

DearBot is available under the [MIT License](LICENSE).
