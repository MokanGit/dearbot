import os
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.config import settings
from backend.app.models import Document


INTERNAL_PATTERNS = [
    "strategy",
    "tailoring",
    "rules",
    "readme",
    "internal",
    "confidential",
    "review copy",
    "draft",
    "master evidence bank",
    "master evidence",
]


def classify_document(filename: str, title: str, content: str = "") -> str:
    """
    Classifies documents into 'internal' vs 'public' with a fail-closed default:
    - Default is 'internal' to prevent accidental disclosure.
    - Only explicitly designated public files or files containing '# classification: public' become public.
    """
    first_lines = (content[:500] if content else "").lower()
    fn_title = f"{filename} {title}".lower()

    # Explicit internal indicators in filename/title
    for pattern in INTERNAL_PATTERNS:
        if pattern in fn_title:
            return "internal"

    # Explicit classification directives in content header
    if "# classification: internal" in first_lines or "classification: internal" in first_lines or "confidential" in first_lines:
        return "internal"

    # Explicit public marker
    if "# classification: public" in first_lines or "classification: public" in first_lines:
        return "public"

    # Explicitly named public profile files. Person-specific names must not be
    # embedded in the application; deployments may add their own prefixes.
    known_public_prefixes = [
        "01_executive_overview",
        "02_selected_experience",
        "03_ai_and_data_governance",
        "04_cybersecurity_and_grc",
        "executive_overview",
        "public_cv",
    ]
    fname_low = filename.lower()
    for pub_prefix in known_public_prefixes:
        if pub_prefix in fname_low:
            return "public"

    # Default-deny / fail-closed
    return "internal"


# Fictional seed material used only for offline development and tests. Real
# career evidence belongs in the ignored synced-docs directory or an external
# source such as Google Drive.
SEED_PROFESSIONAL_DOCS = [
    {
        "google_file_id": "seed_executive_overview",
        "filename": "01_executive_overview.md",
        "title": "Executive Overview & Leadership Profile",
        "classification": "public",
        "content_markdown": """# Classification: public
# Sample Candidate — Fictional Development Profile

## Leadership & Strategic Focus
Sample Candidate is a fictional technology leader included to demonstrate DearBot without exposing a real person's career history.

### Core Competencies
- **Technology strategy:** Translating business goals into a practical platform roadmap.
- **Engineering leadership:** Supporting multidisciplinary product and engineering teams.
- **Responsible AI:** Establishing reviewable, evidence-based uses of generative AI.
"""
    },
    {
        "google_file_id": "seed_selected_experience",
        "filename": "02_selected_experience.md",
        "title": "Selected Experience — Fictional Example",
        "classification": "public",
        "content_markdown": """# Classification: public
# Example Systems — Director of Technology (2022–2024)

## Role Overview
Fictional role used to exercise DearBot's document ingestion and evidence-linking behavior.

- Defined a two-year platform modernization roadmap.
- Introduced measurable reliability objectives and regular service reviews.
- Coordinated engineering, security, and product planning.
"""
    },
    {
        "google_file_id": "seed_ai_data_governance",
        "filename": "03_ai_and_data_governance.md",
        "title": "AI, Machine Learning & Data Governance",
        "classification": "public",
        "content_markdown": """# Classification: public
# AI & Data Governance — Fictional Example

## Practical AI Implementations
- Prototyped an evidence-linked knowledge assistant with human review.
- Defined evaluation criteria for factuality, privacy, and operational ownership.

## Governance & Ethics Principles
- **Separation of concerns:** Keep factual source documents separate from generated prose.
- **Auditability:** Retain source references for material claims.
"""
    }
]


def compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class GoogleDriveService:
    """Service to ingest and synchronize Markdown documents from Google Drive."""

    def __init__(self):
        self.folder_id = settings.GOOGLE_DRIVE_FOLDER_ID
        self.credentials_file = settings.GOOGLE_CREDENTIALS_FILE
        self.service_account_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE
        self.local_sync_dir = settings.LOCAL_SYNC_DIR
        os.makedirs(self.local_sync_dir, exist_ok=True)

    def _get_drive_client(self):
        """Try to build authenticated Google Drive client if credentials exist."""
        try:
            if self.service_account_file and os.path.exists(self.service_account_file):
                from google.oauth2 import service_account
                from googleapiclient.discovery import build
                creds = service_account.Credentials.from_service_account_file(
                    self.service_account_file,
                    scopes=['https://www.googleapis.com/auth/drive.readonly']
                )
                return build('drive', 'v3', credentials=creds)

            if self.credentials_file and os.path.exists(self.credentials_file):
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                creds = Credentials.from_authorized_user_file(
                    self.credentials_file,
                    scopes=['https://www.googleapis.com/auth/drive.readonly']
                )
                return build('drive', 'v3', credentials=creds)
        except Exception as e:
            print(f"Warning: Could not initialize live Google Drive client: {e}")
        return None

    def fetch_drive_markdown_files(self) -> List[Dict[str, str]]:
        """
        Fetch all markdown files from the configured folder.
        Falls back to local synced_docs or seed files if Google credentials are not set.
        """
        # Tests must never depend on a developer's local Drive credentials or
        # cached CV files. They use the explicitly fictional seed corpus.
        if settings.ENV.lower() in ("test", "testing"):
            return SEED_PROFESSIONAL_DOCS

        drive = self._get_drive_client()
        docs = []

        if drive:
            try:
                # Query all files in the designated folder
                query = f"'{self.folder_id}' in parents and trashed = false"
                results = drive.files().list(
                    q=query,
                    fields="files(id, name, mimeType, modifiedTime)",
                    pageSize=100
                ).execute()
                items = results.get("files", [])

                for item in items:
                    file_id = item["id"]
                    name = item["name"]
                    mime_type = item.get("mimeType", "")

                    # Skip subfolders (e.g. Applications folder)
                    if mime_type == "application/vnd.google-apps.folder":
                        continue

                    content = ""
                    try:
                        if mime_type == "application/vnd.google-apps.document":
                            # Export Google Doc to markdown or plain text
                            export = drive.files().export(fileId=file_id, mimeType="text/plain").execute()
                            content = export.decode("utf-8", errors="replace")
                            if not name.endswith(".md"):
                                name = f"{name}.md"
                        else:
                            # Direct download for .md or text files
                            data = drive.files().get_media(fileId=file_id).execute()
                            content = data.decode("utf-8", errors="replace")
                    except Exception as fe:
                        print(f"Warning: Could not fetch file {name} ({file_id}): {fe}")
                        continue

                    # Save local copy to synced_docs for local cache & inspection
                    try:
                        os.makedirs(self.local_sync_dir, exist_ok=True)
                        local_path = os.path.join(self.local_sync_dir, name)
                        with open(local_path, "w", encoding="utf-8") as lf:
                            lf.write(content)
                    except Exception as ce:
                        print(f"Notice: Could not write local cache file {name}: {ce}")

                    title = name.replace(".md", "").replace("_", " ").title()
                    classification = classify_document(name, title, content)
                    docs.append({
                        "google_file_id": file_id,
                        "filename": name,
                        "title": title,
                        "content_markdown": content,
                        "classification": classification,
                    })
                return docs
            except Exception as e:
                print(f"Error fetching from Google Drive API: {e}. Falling back to local files.")

        # Check local sync dir for any .md files
        if os.path.exists(self.local_sync_dir):
            local_files = [
                f for f in os.listdir(self.local_sync_dir)
                if f.endswith(".md") and not f.startswith(".")
            ]
            if local_files:
                for fname in sorted(local_files):
                    fpath = os.path.join(self.local_sync_dir, fname)
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    title = fname.replace(".md", "").replace("_", " ").title()
                    classification = classify_document(fname, title, content)
                    docs.append({
                        "google_file_id": f"local_{fname}",
                        "filename": fname,
                        "title": title,
                        "content_markdown": content,
                        "classification": classification,
                    })
                return docs

        # In production, do not inject synthetic seed documents if Drive and local cache fail
        if settings.ENV.lower() == "production":
            print("Notice: Production environment cannot reach Google Drive and no local files exist. Retaining existing database documents.")
            return []

        # Fallback to seed docs (development & testing only)
        return SEED_PROFESSIONAL_DOCS

    async def sync_documents(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Synchronize documents into the database using content hash diffing.
        Only modified or new documents are written.
        """
        fetched = self.fetch_drive_markdown_files()
        if not fetched:
            return {"status": "no_updates", "synced_count": 0, "message": "No new documents fetched or sync unavailable."}

        added = 0
        updated = 0
        unchanged = 0

        now = datetime.now(timezone.utc)
        fetched_ids = set()

        for item in fetched:
            file_id = item["google_file_id"]
            fetched_ids.add(file_id)
            content = item["content_markdown"]
            content_hash = compute_sha256(content)
            inferred_cls = item.get("classification") or classify_document(item["filename"], item["title"], content)

            # Check if document already exists
            stmt = select(Document).where(Document.google_file_id == file_id)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.is_active = True
                # Preserve manual admin classification overrides
                if existing.classification_source != "admin_override":
                    existing.classification = inferred_cls

                if existing.content_hash == content_hash:
                    unchanged += 1
                    existing.last_synced = now
                else:
                    existing.title = item["title"]
                    existing.filename = item["filename"]
                    existing.content_markdown = content
                    existing.content_hash = content_hash
                    existing.last_modified = now
                    existing.last_synced = now
                    updated += 1
            else:
                new_doc = Document(
                    google_file_id=file_id,
                    title=item["title"],
                    filename=item["filename"],
                    content_markdown=content,
                    content_hash=content_hash,
                    classification=inferred_cls,
                    classification_source="auto_default",
                    is_active=True,
                    last_modified=now,
                    last_synced=now
                )
                session.add(new_doc)
                added += 1

        # Deletion reconciliation: Mark documents removed from Drive as inactive
        stmt_all_docs = select(Document)
        all_db_docs = (await session.execute(stmt_all_docs)).scalars().all()
        for d in all_db_docs:
            if d.google_file_id not in fetched_ids and d.is_active:
                d.is_active = False
                d.last_synced = now

        await session.commit()

        # Retrieve all currently active documents
        stmt_all = select(Document).where(Document.is_active == True).order_by(Document.filename)
        all_docs = (await session.execute(stmt_all)).scalars().all()

        return {
            "status": "success",
            "total_documents": len(all_docs),
            "added": added,
            "updated": updated,
            "unchanged": unchanged,
            "documents": [
                {
                    "id": d.id,
                    "title": d.title,
                    "filename": d.filename,
                    "classification": d.classification,
                    "classification_source": d.classification_source,
                    "manually_approved_at": d.manually_approved_at.isoformat() if d.manually_approved_at else None,
                    "is_active": d.is_active,
                    "content_hash": d.content_hash[:8],
                    "last_synced": d.last_synced.isoformat()
                } for d in all_docs
            ]
        }

