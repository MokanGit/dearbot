# Changelog

Notable changes to DearBot are documented here. The project follows semantic versioning once the first public release is published.

## Unreleased

### Changed

- Renamed the planned public repository to `MokanGit/dearbot`.
- Replaced installation-specific defaults and seeded career history with fictional sample data.
- Made Microsoft Entra optional for local development through explicit authentication modes.
- Changed Entra administration to use DearBot API access tokens and immutable object identifiers instead of ID tokens, Graph audiences, or email authorization.
- Added a complete documentation set for development, configuration, authentication, architecture, deployment, privacy, contribution, security, and publication.
- Added a resumable beginner onboarding skill, master-evidence template, and deterministic evidence validation tools; moved Google Drive and Obsidian guidance to advanced integrations.
- Added a production deployment skill that separates DearBot's portable runtime contract from Hetzner-specific SSH, Caddy, Tailscale, storage-path, and legacy naming assumptions.
- Moved the presentation QR code from the generic landing page to each tokenized application profile and made it encode that profile's exact URL.
- Preserved the GitHub Pages header and footer as a responsive sticky-header page shell.
- Renamed container, ingress, and remote deployment examples from legacy `cv-*` identifiers to `dearbot-*`.
- Added reproducible Python and pnpm dependency declarations plus CI, CodeQL, and Dependabot configuration.

### Security

- Production rejects disabled administrative authentication.
- Production API documentation is disabled by default.
- CORS and trusted hosts are configured by explicit allowlists.
- Browser token caching no longer uses persistent local storage.
- Job URL fetching rejects non-public destinations and revalidates bounded redirects.
- Uploads are checked by file signature or document structure before storage.
- Downloads use attachment disposition, `nosniff`, and private/no-store caching.
- Backend, frontend, and Caddy examples include versioned security-header policies.
- Updated Next.js and vulnerable transitive packages after a clean dependency audit.
