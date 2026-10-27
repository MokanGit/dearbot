# Public repository checklist

The target repository is `MokanGit/dearbot`. Create it privately first and make it public only after every blocking item below is complete.

## Source and history

- [ ] Select and tag an exact source commit in the private repository.
- [ ] Export tracked files into a new repository with fresh Git history.
- [ ] Do not mirror branches, tags, pull-request refs, or Git LFS objects.
- [ ] Confirm all fixtures are fictional and all repository URLs target `MokanGit/dearbot`.
- [ ] Retain this private repository as an internal archive.

## Privacy and secrets

- [ ] Scan the current tree and the private repository's history for secrets.
- [ ] Rotate any credential that has ever been committed or shared unexpectedly.
- [ ] Search for real names, email addresses, phone numbers, tenant IDs, domains, CV facts, and generated application text.
- [ ] Confirm ignored runtime directories contain no tracked personal files; retain only reviewed fictional fixtures and `.gitkeep` placeholders.
- [ ] Review container layers and release artifacts for copied `.env` or data files.

## Security

- [x] Production refuses `AUTH_MODE=disabled`.
- [x] Entra accepts only DearBot API access tokens with the required audience, tenant, permission, and object ID policy.
- [ ] Job URL fetching blocks loopback, private, link-local, metadata, and unsafe redirects in application code; verify that production egress also blocks DNS-rebinding connections.
- [x] Upload and download paths enforce type, content, size, filename, and attachment policies.
- [ ] CORS, trusted hosts, proxy trust, security headers, request limits, and production API documentation have been reviewed at runtime.
- [ ] Dependency, container, and static-analysis scans pass.

## Documentation and community

- [ ] README quickstart works from a clean clone without cloud credentials.
- [x] License, security policy, contributing guide, code of conduct, changelog, architecture, authentication, privacy, and deployment documentation are current.
- [ ] GitHub Pages is reviewed under the new repository path.
- [ ] Vulnerability reporting is configured before publication.

## GitHub settings

- [ ] Protect `main` and require pull-request checks.
- [ ] Enable Dependabot, secret scanning, push protection, and CodeQL.
- [ ] Disable unused repository features and restrict Actions permissions.
- [ ] Add topics, description, license detection, and a first release.

## Final gate

- [x] Backend tests and frontend production build pass.
- [ ] A clean-machine Docker smoke test passes.
- [ ] The repository tree and rendered GitHub pages receive a final manual privacy review.
- [ ] The owner explicitly approves changing repository visibility to public.
