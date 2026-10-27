# Advanced integrations

Complete [beginner onboarding](onboarding.md) before adding another evidence source. DearBot's supported baseline is a reviewed set of local Markdown files under `backend/data/synced_docs/`.

## Google Drive synchronization

Google Drive is optional. It requires a deliberately scoped folder, read-only credentials, and review of the local cache before public classification. Configuration uses `GOOGLE_DRIVE_FOLDER_ID`, `GOOGLE_SERVICE_ACCOUNT_FILE`, or `GOOGLE_CREDENTIALS_FILE`; the synchronization implementation is in `backend/app/services/google_drive.py`.

The helper `scripts/sync_drive.sh` also contains remote-deployment behavior. Do not use it as a beginner import command. Verify its destination and runtime configuration before running it.

## Obsidian generation

Obsidian integration is not part of the core application or beginner onboarding package. Treat it as a separate transformation layer that exports reviewed Markdown into DearBot's local evidence directory.

Do not point DearBot at an entire vault. Vaults commonly contain private notes, attachments, templates, plugin metadata, and unrelated personal data. An advanced integration should instead:

1. Select an explicit folder or tagged note set.
2. render or export stable Markdown without plugin-only syntax;
3. preserve source identifiers and modification times;
4. write to a staging directory;
5. validate and review changes before replacing active evidence; and
6. keep the resulting master evidence bank internal by default.

Google Drive and Obsidian must never be configured as simultaneous writers to the same evidence files without a documented conflict-resolution policy.
