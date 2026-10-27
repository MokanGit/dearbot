# DearBot security review

## Executive summary

The repository cleanup now provides secure production authentication defaults,
strict Entra access-token validation, explicit CORS and host policy, bounded and
content-validated uploads, download hardening, application and frontend security
headers, SSRF destination checks, exact Python dependency versions, and automated
CI, Dependabot, and CodeQL configuration.

No confirmed critical or high-severity finding remains in the reviewed paths.
One infrastructure-dependent SSRF limitation remains: the application validates
DNS before connecting, but the HTTP client performs its own DNS lookup. Production
deployment must therefore deny private and metadata destinations at the egress
layer. This is a deployment gate, not a reason to weaken the current checks.

## Medium severity

### SEC-001 — Outbound URL validation cannot pin the connection address

- **Rule:** FASTAPI-SSRF-001
- **Location:** `backend/app/services/job_tailor.py`, `_validate_public_http_url` and `_safe_get`, lines 62–123
- **Evidence:** the hostname is resolved and checked before `httpx` performs a separate connection-time resolution.
- **Impact:** a hostile DNS service could theoretically return a public address during validation and a private address during connection.
- **Fix:** enforce an egress proxy or firewall policy that rejects loopback, private, link-local, and metadata ranges. Alternatively, introduce a reviewed HTTP transport that connects to the validated address while preserving HTTPS SNI and the original `Host`.
- **Mitigation:** the application rejects credentials, nonstandard ports, literal and DNS-resolved non-public addresses, revalidates redirects, bounds redirects and response sizes, and applies short timeouts.
- **False-positive notes:** risk is substantially reduced when the container cannot route to internal services or cloud metadata.

## Low severity

### SEC-002 — Frontend CSP retains inline allowances

- **Rule:** NEXT-CSP-001 / REACT-HEADERS-001
- **Location:** `frontend/next.config.mjs`, lines 13–24
- **Evidence:** the production CSP includes `'unsafe-inline'` for scripts and styles for compatibility with the current Next.js application shell.
- **Impact:** CSP provides less protection against a successful HTML injection than a nonce- or hash-based policy.
- **Fix:** migrate to per-request nonces when the deployment architecture supports them, then remove the inline allowances.
- **Mitigation:** React escapes text by default; the review found no untrusted raw-HTML rendering path, and framing, object embedding, base URL, form targets, and connection destinations are restricted.

### SEC-003 — Exact Python lock does not include artifact hashes

- **Rule:** FASTAPI-SUPPLY-001
- **Location:** `backend/requirements.txt`
- **Evidence:** every resolved package version is exact, but package artifact hashes are not recorded.
- **Impact:** a compromised package index or replaced artifact is not detected by pip's `--require-hashes` mode.
- **Fix:** adopt a hash-generating lock workflow such as `pip-compile --generate-hashes` and install with `--require-hashes`.
- **Mitigation:** CI and the production container use the exact lock; Dependabot and CodeQL configurations are included.

## Remediated during cleanup

- Removed hard-coded tenant, client, email, personal-profile, employer, and domain values.
- Made disabled authentication development/test-only; production fails closed.
- Restricted Entra to the configured issuer, API audience, algorithm, permission, and optional immutable object IDs.
- Removed ID-token fallback and persistent browser token storage.
- Added explicit CORS, trusted-host, and proxy-header trust configuration.
- Disabled API documentation endpoints in production.
- Added SSRF protocol, credential, port, address, redirect, timeout, and response-size controls.
- Added signature/structure validation for PDF, Office, OpenDocument, text, RTF, and image uploads.
- Added attachment disposition, `nosniff`, and private/no-store download policy.
- Added versioned backend, frontend, and edge security-header policy.
- Added an exact Python dependency lock and reproducible frontend package-manager declaration.
- Updated Next.js to `15.5.28` and patched vulnerable `sharp` and `source-map-js` transitive versions; `pnpm audit --audit-level high` reports no known vulnerabilities.
- Added CI, Dependabot, and CodeQL configuration for the future public repository.
