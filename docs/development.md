# Development

## Docker workflow

```bash
cp .env.example .env
./local_docker.sh
```

This uses fictional seed evidence, the offline mock model, and disabled local authentication.

For a first real candidate setup, use the [beginner onboarding](onboarding.md) workflow. Google Drive and Obsidian are intentionally excluded from that path.

## Native backend

```bash
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.lock
pytest backend/tests
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

`--reload` is for local development only.

`backend/requirements.txt` records the supported direct dependency ranges.
`backend/requirements.lock` is the reviewed exact environment used by CI and
the production container. Refresh it deliberately when dependencies change,
then run the complete test suite.

## Native frontend

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

For a production-equivalent check, run `pnpm build` followed by `pnpm start`.

## Test data

Tests and seeds must use fictional identities and companies. Local real-world data belongs only in ignored runtime directories. Before committing, inspect `git status`, `git diff --cached`, and the output of a secret scanner.

## Documentation site

```bash
python3 -m http.server 4173 --directory docs
```

Open <http://localhost:4173>. The static site is intended for GitHub Pages after the new public repository is ready.
