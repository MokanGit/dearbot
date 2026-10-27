---
name: dearbot-deploy
description: Plan, validate, migrate, or deploy DearBot to a Docker host or container platform while separating the portable runtime contract from the repository's Hetzner-era SSH, Caddy, Tailscale, path, and container-name assumptions. Use for production deployment, host migration, reverse-proxy setup, or reviewing whether a target environment can run DearBot; do not use for ordinary local development.
---

# DearBot Deployment

Deploy DearBot without treating the current Hetzner installation as the universal architecture. Preserve existing installations until a new target has passed health, data, routing, authentication, and rollback checks.

## Authorization boundary

A request for a plan or review authorizes read-only inspection, not remote changes. Before building, pushing, uploading, starting containers, editing DNS or proxy configuration, copying production data, or stopping services, confirm that the user requested execution and identify the exact target.

Never print secret values, container environments, private CV contents, database contents, or access tokens. Do not use broad `docker inspect` or rendered Compose output when it may expose environment values.

## Select the path

Always read `references/runtime-contract.md`.

- For the existing server, an upgrade from legacy `cv-*` resources, or a migration away from Hetzner, also read `references/hetzner-delta.md`.
- For a new Docker VM or managed container platform, read `references/target-environments.md`.

## Workflow

1. Establish whether the task is assessment, deployment, migration, or rollback. Record the target host/platform, domain, architecture, reverse proxy, persistence, identity provider, and acceptable downtime.
2. Inspect the repository status and exact commit to deploy. Do not deploy an uncommitted tree unless the user explicitly requests it and understands that it is not reproducible.
3. Inventory the target read-only. The helper `scripts/host-inventory.sh` is safe to run on a Docker host; it intentionally omits environment values and file contents. Obtain permission before executing it remotely.
4. Compare the inventory with the runtime contract. Produce a concrete gap list before making changes.
5. Choose immutable image names and versions. DearBot needs separate backend and frontend images. The frontend standalone bundle must be built before its Docker image because `frontend/Dockerfile` copies `frontend/.next/standalone` rather than compiling source.
6. Prepare configuration outside Git. Treat `NEXT_PUBLIC_*` values as frontend build inputs; setting them only in a runtime environment file does not reliably change browser-bundled values.
7. Validate locally or in CI: backend tests, frozen frontend install, frontend production build, Docker image builds, and `docker compose config --quiet` where supported. Avoid printing a rendered configuration containing secrets.
8. Back up persistent data and verify a restore method. For SQLite, do not copy an active database and WAL files as an ordinary live directory copy; use a consistent database backup or stop writers first.
9. Deploy alongside the existing installation when migrating. Use distinct container names, network aliases, storage paths, and a temporary hostname until verification succeeds.
10. Verify container health, public profile routing, document downloads, API/MCP routing, admin authentication, supported and unsupported evidence questions, persistence, logs, and backup restoration.
11. Validate proxy configuration before an atomic cutover. Keep the previous upstream and images available for rollback.
12. Report the deployed commit, image digests, configuration locations, data location, health results, cutover performed, and exact rollback action. Do not declare success from container start alone.

## Stop conditions

Stop before mutation when any of these are unknown: persistent data location, backup/restore path, current proxy upstreams, production authentication configuration, target DNS/TLS ownership, or rollback route. Stop after a failed health or migration check; do not continue to proxy cutover.
