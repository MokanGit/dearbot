# Target environment choices

Choose the simplest topology that satisfies the runtime contract and the operator's recovery capabilities.

## Existing Docker host and reverse proxy

Use the host's established proxy and network conventions. Deploy the two DearBot images, mount durable backend storage, and translate the routing table into the existing Caddy, Nginx, or Traefik configuration. Do not add a second proxy that competes for ports 80/443.

## Self-contained Docker host

Supply a Compose project with frontend, backend, and one TLS reverse proxy. Use named or explicitly managed host volumes, pinned image digests, external secret files, log rotation, health checks, and backup automation. A bundled Caddy service is appropriate only when no existing ingress owns the public ports.

## Managed container platform

Confirm support for two independently routed services, durable storage or external database/document storage, build-time public frontend variables, long-lived streaming responses, request timeouts, TLS, and restricted administrative routing. Ephemeral filesystems are not sufficient for the default backend design.

Avoid scaling the backend horizontally while it uses the default SQLite/data-directory model. Move database and document persistence to services that support the intended replica count first.

## Kubernetes

Use separate Deployments and Services for frontend and backend, an Ingress implementing the route split, Secrets/ConfigMaps with appropriate separation, and a deliberate persistent-data strategy. Do not treat a single ReadWriteOnce SQLite volume as a horizontally scalable database.

## Serverless platforms

The frontend may fit a serverless environment, but the backend's persistent files, generated documents, streaming endpoints, and default SQLite design require adaptation. Do not claim full support without replacing those stateful assumptions and verifying timeout behavior.
