# DearBot project site

This directory contains the buildless static project site prepared for GitHub Pages. Relative asset paths allow it to run locally and, after publication, under:

`https://mokangit.github.io/dearbot/`

The page shell is intentional: preserve the sticky `.site-header` and the
bottom `.site-footer` when changing or regenerating the landing page.

## Preview locally

```bash
python3 -m http.server 4173 --directory docs
```

Open <http://localhost:4173>.

## Publish later

Do not enable Pages from this private cleanup repository. After the sanitized `MokanGit/dearbot` repository has passed [the publication checklist](publication-checklist.md):

1. Open **Settings → Pages**.
2. Choose **Deploy from a branch**.
3. Select `main` and `/docs`.
4. Verify navigation, repository links, accessibility, and the personality-test prototype.

No site build command is required.
