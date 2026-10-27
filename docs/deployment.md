# Deployment

DearBot can remain self-hosted on Hetzner or run on another container platform. The important boundary is operational, not vendor-specific: public profile traffic and administrative traffic must not share an unauthenticated control plane.

## Production prerequisites

- TLS-terminating reverse proxy.
- Persistent database and generated-document storage with tested backups.
- `ENV=production` and `AUTH_MODE=entra`.
- Explicit host and CORS allowlists.
- Runtime secrets supplied outside the image and repository.
- Request-size limits, timeouts, and rate limits at the proxy.
- A current, pinned container release.

## Included deployment files

- `deploy/docker-compose.prod.yml`: two containers on an external proxy network.
- `deploy/Caddyfile.snippet`: public profile routing and a separate administrative ingress example.
- `deploy/runtime.cv.env.example`: production configuration template.
- `deploy/deploy_cv.sh`: an operator convenience script for an existing Docker host.

Review and adapt these examples; they are not infrastructure-as-code for a universal production environment.

For AI-guided assessment, migration, or deployment, use `skills/dearbot-deploy/SKILL.md`. It defines the portable runtime contract and the explicit differences between a new target and the existing Hetzner-era installation.

## Hetzner recommendation

Keeping the demonstration instance on Hetzner is reasonable. Build immutable images in CI, publish them to a registry, and let the server pull versioned digests. Keep the runtime environment, database, synchronized evidence, and generated documents on the server. Public CI should not have database access.

The current repository examples use `/opt/apps/dearbot` and `dearbot-*` container names. Historical installations may still use `/opt/apps/cv` and `cv-*`. Treat that rename as a planned migration; do not run the current helper as an assumed in-place upgrade.

## Administrative exposure

The example Caddy configuration keeps `/admin` off the public ingress and exposes it through a private network while FastAPI independently validates Entra access tokens. Either control may fail without making the other optional.

## Outbound network policy

The job-ad importer accepts external URLs. Production egress must reject
loopback, RFC1918/private, link-local, and cloud-metadata destinations even after
DNS resolution. The application performs the same checks before each request
and redirect, but a firewall or egress proxy closes the remaining DNS-rebinding
gap between validation and connection.

## Backups and recovery

Back up the database, canonical evidence, and generated packages. Test restoration. Repository history is not a backup for runtime data and must never contain it.
