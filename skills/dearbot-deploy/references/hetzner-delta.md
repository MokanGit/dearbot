# Hetzner installation delta

The application has no dependency on the Hetzner API. The existing deployment pattern is an ordinary SSH-accessible Linux Docker host, but its operational names and surrounding infrastructure are installation-specific.

## Assumptions inherited from the current host

- Deployment is performed over SSH and SCP.
- Images are built locally and streamed with `docker save | ssh ... docker load` instead of pulled from a registry.
- Application state is stored below `/opt/apps/...` on the host.
- An external Docker network named `apps-proxy` already exists.
- A separately managed Caddy container joins that network.
- Caddy owns ports 80/443 and TLS certificates.
- Administrative routing may use Tailscale/private addresses in addition to Entra validation.
- The deployment helper tries Caddy container names `shared-caddy` and `caddy`.

These are not requirements for a new provider.

## Legacy-to-current rename

Historical deployments used:

- `/opt/apps/cv`;
- `cv-backend` and `cv-frontend`;
- `cv-backend:latest` and `cv-frontend:latest`; and
- Caddy upstream aliases `cv-backend` and `cv-frontend`.

Current repository examples use `/opt/apps/dearbot` and `dearbot-*` names. Running the current helper against a legacy installation is not an in-place upgrade: it creates a parallel installation and may start it with an empty runtime file or data directory while Caddy continues to route to the legacy aliases.

## Required inventory

Before changing the current server, determine without printing secrets:

- active Compose projects, container names, images, and health;
- mounts and Docker-network aliases for the CV/DearBot containers;
- whether `/opt/apps/cv` or `/opt/apps/dearbot` holds authoritative data;
- the active Caddy upstream names and public/private hostnames;
- the runtime environment file location and required key names, not their values;
- how SQLite is backed up consistently;
- current DNS and certificate ownership; and
- the last known-good image identifiers.

Do not use unrestricted `docker inspect`, `docker compose config`, or `cat runtime.env` in captured output because they can reveal secrets.

## Safe migration shape

1. Back up the legacy data and runtime configuration with restricted permissions.
2. Deploy `dearbot-*` containers side by side using a copied, consistent data snapshot and a temporary hostname.
3. Validate application behavior and authentication against the temporary hostname.
4. Validate the updated Caddy configuration before reload.
5. Switch upstreams atomically while retaining the `cv-*` containers and old configuration.
6. Monitor, then remove legacy resources only after an agreed rollback window.

If the goal is only to update application code on the current installation, preserving the legacy names and paths is safer than combining an application upgrade with an infrastructure rename.
