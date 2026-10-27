# Contributing to DearBot

Thank you for helping make evidence-grounded applications easier to inspect and improve.

## Before opening a change

- Search existing issues and pull requests.
- Keep real CVs, application material, credentials, databases, and generated PDFs out of Git.
- Discuss large architectural or data-model changes before implementation.
- Report vulnerabilities privately according to [SECURITY.md](SECURITY.md).

## Development workflow

1. Create a focused branch from `main`.
2. Copy `.env.example` to `.env`; keep `LLM_PROVIDER=mock` and `AUTH_MODE=disabled` for ordinary local work.
3. Add tests for behavior changes.
4. Run `pytest backend/tests` and `pnpm build` in `frontend/`.
5. Update documentation and `CHANGELOG.md` when configuration or public behavior changes.

Pull requests should explain the problem, the chosen approach, verification performed, privacy impact, and any operational migration required.

## Evidence and examples

Examples must be fictional and clearly identified as such. Do not contribute a real person's contact details, employment history, private application notes, or copied job advertisements without permission.

Generated claims must remain traceable to supplied evidence. A change that improves prose while weakening factual validation is a regression.

## Style

- Python: type annotations where they improve clarity; keep FastAPI validation explicit.
- TypeScript: avoid `any` in new code and validate untrusted runtime data.
- Documentation: concise, provider-neutral, and accurate to the current implementation.
- Security: fail closed in production and never place secrets in browser-visible variables.

By contributing, you agree that your contribution is licensed under the repository's MIT License.
