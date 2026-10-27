# Portable runtime contract

DearBot's application layer is provider-agnostic. Its operational contract is not a single stateless container.

## Workloads

| Workload | Internal port | Persistence | Notes |
| --- | ---: | --- | --- |
| Frontend | 3000 | None | Next.js standalone server; browser-visible `NEXT_PUBLIC_*` values are build-sensitive. |
| Backend | 8000 | `/app/backend/data` for the default SQLite design | FastAPI running as UID/GID 10001 in the supplied image. |

The default production Compose example uses two images, an external Docker network named `apps-proxy`, and a host-mounted data directory. A platform may replace those mechanisms, but it must preserve the behavior.

## Persistent data

The default data tree contains the SQLite database, synchronized evidence, generated CVs, applications, and application media. It may contain sensitive personal data and must never be copied into an image, repository, public CI artifact, or log.

Use durable storage with backups. A managed platform must support a persistent volume or externalize the database and document storage. Multiple backend replicas are unsafe with an ordinary single-file SQLite volume unless the storage and application topology are deliberately redesigned.

## Routing

The public origin must route:

- `/`, `/_next/*`, and `/a/{token}` profile pages to the frontend;
- `/a/{token}/*` API subresources and document downloads to the backend;
- `/mcp/*` and `/health` to the backend.

The admin UI is served by the frontend while admin API routes are served by the backend. Do not expose the admin control plane publicly without the configured identity checks. The provided Caddy snippet is an example, not a required proxy implementation; Nginx, Traefik, a cloud load balancer, or managed ingress may provide equivalent routing and headers.

## Production configuration

At minimum, production needs canonical public/API origins, explicit host and CORS allowlists, persistent storage, model-provider configuration, and secrets outside the images. The current application rejects disabled authentication in production and expects a complete supported authentication configuration.

Apply request-size limits, timeouts, TLS, security headers, rate limiting, and an egress control that blocks private, link-local, loopback, and cloud-metadata destinations for the job-URL importer.

## Images and builds

The backend image installs `backend/requirements.lock` and copies application source. The frontend image copies an already-built `.next/standalone` tree. A clean image pipeline therefore needs this order:

1. frozen frontend dependency installation;
2. frontend production build with browser-visible configuration available;
3. frontend Docker build from repository context;
4. backend Docker build from repository context; and
5. immutable tags or digests in the deployment definition.

The repository CI currently verifies code but does not publish images or deploy production.

## Minimum acceptance checks

- Both workloads remain healthy after restart.
- Public profile HTML, JSON discovery, downloads, Q&A, and MCP reach the correct workload.
- `/admin` follows the intended private/public access policy and rejects invalid tokens.
- A supported question returns approved evidence and an unsupported claim returns no verified evidence.
- New runtime data survives container replacement.
- Backup restoration is demonstrated, not merely configured.
