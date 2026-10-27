# Beginner onboarding

The beginner path creates a private local master CV and runs DearBot with Docker, fictional model responses, and development-only authentication. It does not require cloud credentials, Microsoft Entra, Google Drive, Obsidian, or a paid AI provider.

## AI-guided setup

Ask your AI coding tool to use the repository skill directly:

> Read `skills/dearbot-onboard/SKILL.md` and guide me through DearBot beginner onboarding using only the career documents I explicitly provide.

Tools that support repository skills may discover `dearbot-onboard` automatically. The skill is resumable: it checks the environment and existing ignored evidence files before deciding what remains.

## What you need

- Docker with Compose.
- A clean DearBot checkout.
- One or more CVs or other career documents whose facts you can verify.
- Time to confirm employers, relationships, titles, dates, metrics, education, and certifications.

Do not put real career documents in Git-tracked folders. The onboarding skill writes candidate evidence under `backend/data/synced_docs/`, which is ignored by Git.

## Beginner workflow

1. Copy `.env.example` to `.env`.
2. Keep the development defaults: mock model, disabled local authentication, and local Markdown evidence.
3. Build `00_master_evidence_bank.md` from the supplied evidence and resolve factual conflicts.
4. Approve a smaller set of facts for explicitly public evidence documents.
5. Validate the internal master and public subsets.
6. Start DearBot with `./local_docker.sh` and synchronize the local evidence.
7. Test one supported question and one unsupported claim.

The master evidence bank is an internal factual ledger, not the document recruiters receive. Job-specific CVs and cover letters are generated later from the verified facts.

## Excluded from the beginner path

Google Drive synchronization and Obsidian-based generation are advanced integrations. They add credentials, synchronization behavior, privacy boundaries, and conflict handling that are unnecessary for a first local run. See [Advanced integrations](advanced-integrations.md) only after the local Markdown workflow is working.
