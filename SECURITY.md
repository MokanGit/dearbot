# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability, exposed credential, or accidental disclosure of candidate data.

Use GitHub's private vulnerability reporting for `MokanGit/dearbot` once the public repository is available. While this repository remains private, contact the repository owner directly through an established private channel.

Include the affected version or commit, impact, reproduction steps, and any suggested remediation. Avoid including real CV content, access tokens, or other personal data in the report unless necessary; redact wherever possible.

## Supported versions

Before the first public release, only the current `main` branch is maintained. After publication, this section will list supported release lines.

## Deployment responsibility

DearBot is designed for a single candidate or trusted operator. It does not provide multi-tenant isolation.

Production operators must:

- enable administrative authentication;
- keep credentials and runtime data outside Git and container images;
- restrict administrative ingress and configure proxy trust correctly;
- patch dependencies and base images;
- define retention, backup, and deletion procedures;
- review public profile tokens as bearer capabilities;
- understand which personal data is sent to enabled model, storage, and tracing providers.

See [Authentication](docs/authentication.md), [Deployment](docs/deployment.md), and [Data and privacy](docs/data-privacy.md).
