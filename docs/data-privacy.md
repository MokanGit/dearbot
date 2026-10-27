# Data and privacy

CVs, cover letters, job searches, interview notes, and recruiter interaction logs are personal data. Some deployments may also process sensitive inferences. The operator is responsible for defining purpose, access, retention, and deletion.

## Repository boundary

The repository may contain fictional fixtures only. The following remain ignored and private:

- `.env` and provider credentials;
- synchronized CV and evidence documents;
- application records and attachments;
- generated PDFs;
- SQLite databases and journals;
- local screenshots, traces, and test artifacts.

## Public profile boundary

Only documents explicitly classified public may support public answers. Treat each `/a/{token}` URL as a bearer capability: anyone with the URL may access its associated profile until it is revoked.

Do not include internal job-search strategy, salary expectations, private recruiter notes, or unapproved source documents in the public evidence set.

## External processors

Model providers, Google Drive, and tracing platforms may receive personal data when enabled. Review their terms, data location, retention, training settings, and subprocessors. Tracing is disabled by default because prompts can contain substantial career material.

## Retention

Archive or revoke expired applications and run cleanup according to the configured retention policy. Confirm that backups and external processors follow compatible deletion schedules.

This document describes the software's data paths; it is not legal advice.
